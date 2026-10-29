"""Question -> validated Intent. Two interpreters:

1. Claude (only if ANTHROPIC_API_KEY set) -> strict JSON -> validated by Pydantic.
2. Rule-based fallback (keywords). Honest about being rules, not AI.
Neither can produce SQL: the Intent model only allows 5 fixed intent names + 2 month strings.
"""
import json
import logging
import re
from typing import Literal

from pydantic import BaseModel, ConfigDict, ValidationError, field_validator, model_validator

from app.config import get_settings
from app.services.analytics import MONTH_RE

log = logging.getLogger("bi.interpreter")

IntentName = Literal["total_revenue", "top_product", "monthly_trend", "top_region", "revenue_comparison"]


class Intent(BaseModel):
    model_config = ConfigDict(extra="forbid")  # unknown fields => rejected
    intent: IntentName
    first_month: str | None = None
    second_month: str | None = None

    @field_validator("first_month", "second_month")
    @classmethod
    def _month(cls, v):
        if v is not None and not MONTH_RE.match(v):
            raise ValueError("month must be YYYY-MM")
        return v

    @model_validator(mode="after")
    def _params(self):
        if self.intent == "revenue_comparison" and not (self.first_month and self.second_month):
            raise ValueError("revenue_comparison needs first_month and second_month")
        if self.intent != "revenue_comparison" and (self.first_month or self.second_month):
            raise ValueError("months are only allowed for revenue_comparison")
        return self


class InterpretationResult(BaseModel):
    intent: Intent | None = None
    method: Literal["claude", "rule_based"] = "rule_based"
    clarification: str | None = None  # set when we cannot confidently answer
    fallback_reason: str | None = None


# ---------------- rule-based fallback ----------------
MONTHS = {m: i for i, m in enumerate(
    ["january", "february", "march", "april", "may", "june", "july", "august",
     "september", "october", "november", "december"], start=1)}
MONTHS.update({k[:3]: v for k, v in list(MONTHS.items())})
DEFAULT_YEAR = 2026  # the dataset covers Jan-Jun 2026


def _find_months(q: str) -> list[str]:
    out = []
    for m in re.finditer(r"\b(?:(\d{4})-(\d{1,2})|(january|february|march|april|may|june|july|august|september|october|november|december|jan|feb|mar|apr|jun|jul|aug|sept?|oct|nov|dec)\b(?:\s+(\d{4}))?)", q):
        if m.group(1):
            out.append((m.start(), int(m.group(1)), int(m.group(2))))
        else:
            name = m.group(3)[:3] if m.group(3) not in MONTHS else m.group(3)
            out.append((m.start(), int(m.group(4) or 0) or None, MONTHS[name]))
    # a bare year after the last month name applies to months without a year ("Feb and March 2026")
    years = re.findall(r"\b(20\d{2})\b", q)
    shared = int(years[-1]) if years else DEFAULT_YEAR
    res = []
    for _, y, mo in sorted(out):
        if not 1 <= mo <= 12:
            raise ValueError(f"invalid month number {mo}")
        res.append(f"{y or shared:04d}-{mo:02d}")
    return res


def interpret_with_rules(question: str) -> InterpretationResult:
    q = question.lower()
    r = lambda intent=None, **kw: InterpretationResult(intent=intent, method="rule_based", **kw)

    if re.search(r"\b(compare|comparison|change|changed|versus|vs|difference|between)\b", q) and re.search(r"revenue|sales|compare|change", q):
        try:
            months = _find_months(q)
        except ValueError as e:
            return r(clarification=f"I couldn't read the months in your question ({e}). Use e.g. 'Compare February and March 2026'.")
        if len(months) != 2 or months[0] == months[1]:
            return r(clarification="To compare revenue I need exactly two different months, e.g. 'Compare February and March 2026'.")
        return r(Intent(intent="revenue_comparison", first_month=months[0], second_month=months[1]))
    if re.search(r"\b(monthly|month by month|per month|trend|by month|each month)\b", q):
        return r(Intent(intent="monthly_trend"))
    if re.search(r"\bregion|\bterritor|\barea\b", q) and re.search(r"best|top|highest|most|perform|sales|revenue|generat|made", q):
        return r(Intent(intent="top_region"))
    if re.search(r"\bproduct|\bitem", q) and re.search(r"best|top|highest|most|perform|sell|revenue|generat|made|money", q):
        return r(Intent(intent="top_product"))
    if re.search(r"total", q) and re.search(r"revenue|sales|income|money", q):
        return r(Intent(intent="total_revenue"))
    if re.search(r"\b(revenue|sales)\b", q) and re.search(r"\b(overall|how much|what is|what's|our)\b", q):
        return r(Intent(intent="total_revenue"))
    return r(clarification=(
        "I can answer: total revenue, top product, monthly revenue trend, top region, and "
        "comparison between two months. Please rephrase your question as one of these."))


# ---------------- Claude interpreter ----------------
SYSTEM_PROMPT = """You convert a business question into a JSON intent. Output ONLY JSON, no prose.
Allowed intents: total_revenue, top_product, monthly_trend, top_region, revenue_comparison.
Schema: {"intent": "<one of the above>", "first_month": "YYYY-MM or null", "second_month": "YYYY-MM or null"}
Months only for revenue_comparison (the data covers 2026-01 to 2026-06; assume 2026 if no year is given).
If the question is not one of the five supported kinds, output {"intent": "unsupported"}.
Never compute numbers. Never output SQL."""


class AIUnavailable(Exception):
    pass


def call_claude(question: str) -> str:
    """Returns raw text from Claude. Separate function so tests can mock it."""
    s = get_settings()
    if not s.anthropic_api_key:
        raise AIUnavailable("no API key configured")
    try:
        import anthropic
        client = anthropic.Anthropic(api_key=s.anthropic_api_key, timeout=s.ai_timeout_seconds, max_retries=0)
        msg = client.messages.create(
            model=s.anthropic_model, max_tokens=150, system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": question}],
        )
        return "".join(b.text for b in msg.content if getattr(b, "type", "") == "text")
    except Exception as e:  # timeouts, auth, network... never log the key
        raise AIUnavailable(type(e).__name__) from e


def parse_claude_output(text: str) -> Intent | None:
    """Validate Claude's text. Returns Intent, None if Claude said 'unsupported'. Raises ValueError if malformed."""
    cleaned = re.sub(r"^```(?:json)?|```$", "", text.strip(), flags=re.M).strip()
    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError as e:
        raise ValueError("Claude output is not valid JSON") from e
    if not isinstance(data, dict):
        raise ValueError("Claude output is not a JSON object")
    if data.get("intent") == "unsupported":
        return None
    try:
        return Intent.model_validate(data)
    except ValidationError as e:
        raise ValueError(f"Claude output failed validation: {e.error_count()} error(s)") from e


def interpret(question: str) -> InterpretationResult:
    if get_settings().anthropic_api_key:
        try:
            intent = parse_claude_output(call_claude(question))
            if intent is None:
                return InterpretationResult(
                    method="claude",
                    clarification="That question isn't one I can answer from the sales data. "
                                  "Try: total revenue, top product, monthly trend, top region, or compare two months.")
            return InterpretationResult(intent=intent, method="claude")
        except (AIUnavailable, ValueError) as e:
            log.warning("Claude interpretation failed (%s); using rule-based fallback", e)
            result = interpret_with_rules(question)
            result.fallback_reason = str(e)
            return result
    result = interpret_with_rules(question)
    result.fallback_reason = "no API key configured"
    return result
