import json

import pytest

from app.services import assistant, question_interpreter as qi


@pytest.mark.parametrize("q,intent", [
    ("What is our total revenue?", "total_revenue"),
    ("Which product made the most money?", "top_product"),
    ("Which product generated the highest revenue?", "top_product"),
    ("Show monthly revenue.", "monthly_trend"),
    ("What is the monthly revenue trend?", "monthly_trend"),
    ("Which region performed best?", "top_region"),
    ("Which region generated the highest sales?", "top_region"),
])
def test_rules_recognise_core_questions(q, intent):
    assert qi.interpret_with_rules(q).intent.intent == intent


def test_rules_compare_months():
    i = qi.interpret_with_rules("Compare February and March 2026").intent
    assert (i.intent, i.first_month, i.second_month) == ("revenue_comparison", "2026-02", "2026-03")
    i = qi.interpret_with_rules("How did revenue change between Jan and Apr?").intent
    assert (i.first_month, i.second_month) == ("2026-01", "2026-04")


def test_compare_with_missing_month_asks_for_clarification():
    r = qi.interpret_with_rules("Compare revenue for March")
    assert r.intent is None and "two different months" in r.clarification


@pytest.mark.parametrize("q", ["What is the weather today?", "'; DROP TABLE sales_transactions; --",
                               "DELETE FROM sales_transactions", "Tell me a joke"])
def test_unsupported_and_injection_like_questions(db, q):
    out = assistant.ask(q)
    assert out["status"] == "unsupported" and out["intent"] is None and out["metrics"] == {}


def test_injection_text_never_reaches_sql(db):
    assistant.ask("total revenue'; DROP TABLE sales_transactions; --")
    import sqlite3, os
    assert sqlite3.connect(os.environ["SALES_DB_PATH"]).execute("SELECT COUNT(*) FROM sales_transactions").fetchone()[0] == 51


def test_parse_claude_valid():
    i = qi.parse_claude_output('```json\n{"intent":"revenue_comparison","first_month":"2026-02","second_month":"2026-03"}\n```')
    assert i.intent == "revenue_comparison"


@pytest.mark.parametrize("bad", [
    "not json at all",
    '["list"]',
    '{"intent": "drop_table"}',
    '{"intent": "total_revenue", "sql": "DELETE FROM x"}',                      # unknown field
    '{"intent": "revenue_comparison", "first_month": "2026-13", "second_month": "2026-02"}',
    '{"intent": "revenue_comparison", "first_month": "2026-01"}',               # missing param
])
def test_malformed_claude_output_rejected(bad):
    with pytest.raises(ValueError):
        qi.parse_claude_output(bad)


def test_claude_unsupported_means_no_guessing(db, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
    monkeypatch.setattr(qi, "call_claude", lambda q: '{"intent":"unsupported"}')
    out = assistant.ask("What is the weather?")
    assert out["status"] == "unsupported" and out["interpretation_method"] == "claude"


def test_claude_success_path_uses_db_numbers(db, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
    monkeypatch.setattr(qi, "call_claude", lambda q: json.dumps({"intent": "total_revenue"}))
    out = assistant.ask("how much have we made?")
    assert out["interpretation_method"] == "claude" and out["status"] == "success"
    assert out["metrics"]["eligible_transactions"] == 48


def test_ai_failure_falls_back_to_rules(db, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
    def boom(q): raise qi.AIUnavailable("TimeoutError")
    monkeypatch.setattr(qi, "call_claude", boom)
    out = assistant.ask("What is our total revenue?")
    assert out["status"] == "success" and out["interpretation_method"] == "rule_based"


def test_malformed_ai_output_and_unclear_question_asks_to_rephrase(db, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
    monkeypatch.setattr(qi, "call_claude", lambda q: "I think revenue is 5")
    out = assistant.ask("hmm tell me stuff")
    assert out["status"] == "unsupported" and "rephrase" in out["answer"].lower()
