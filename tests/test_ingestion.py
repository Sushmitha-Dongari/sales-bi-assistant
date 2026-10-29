import sqlite3

from app.services.ingestion import import_csv


def test_imports_all_51_rows_and_summary_adds_up(tmp_path, monkeypatch):
    monkeypatch.setenv("SALES_DB_PATH", str(tmp_path / "a.db"))
    s = import_csv()
    assert s["source_rows"] == 51
    assert s["by_category"]["returned"] == 1
    assert s["by_category"]["zero_quantity"] == 1
    assert s["by_category"]["missing_or_invalid_price"] == 1
    assert s["analytics_eligible_rows"] == 48
    assert s["rejected_rows"] == 0
    assert sum(s["by_category"].values()) == s["source_rows"]  # no double counting


def test_import_is_idempotent(db):
    s2 = import_csv()
    assert s2["already_present_rows"] == 51 and s2["stored_new_rows"] == 0
    con = sqlite3.connect(db)
    assert con.execute("SELECT COUNT(*) FROM sales_transactions").fetchone()[0] == 51


def test_missing_price_is_null_flagged_and_excluded(db):
    row = sqlite3.connect(db).execute(
        "SELECT unit_price, net_revenue, is_valid, is_eligible, quality_flags FROM sales_transactions "
        "WHERE transaction_id='TXN0051'").fetchone()
    assert row[0] is None and row[1] is None          # not silently 0
    assert row[2] == 0 and row[3] == 0
    assert "missing_unit_price" in row[4]


def test_returned_and_zero_quantity_excluded_but_preserved(db):
    con = sqlite3.connect(db)
    r33 = con.execute("SELECT status, is_eligible FROM sales_transactions WHERE transaction_id='TXN0033'").fetchone()
    r34 = con.execute("SELECT quantity, is_eligible, quality_flags FROM sales_transactions WHERE transaction_id='TXN0034'").fetchone()
    assert r33 == ("Returned", 0)
    assert r34[0] == 0 and r34[1] == 0 and "zero_quantity" in r34[2]


def test_dates_stored_iso(db):
    d = sqlite3.connect(db).execute("SELECT order_date FROM sales_transactions WHERE transaction_id='TXN0001'").fetchone()[0]
    assert d == "2026-01-03"


def test_bad_rows_rejected_explicitly_not_dropped_silently(make_db):
    rows = [
        ["T1", "01-01-2026", "A", "C", "North", "Online", "1", "100", "0", "Completed"],
        ["T1", "02-01-2026", "A", "C", "North", "Online", "1", "100", "0", "Completed"],   # duplicate id
        ["T2", "31-02-2026", "A", "C", "North", "Online", "1", "100", "0", "Completed"],   # bad date
        ["T3", "01-01-2026", "A", "C", "North", "Online", "-2", "100", "0", "Completed"],  # negative qty
        ["T4", "01-01-2026", "A", "C", "North", "Online", "1", "-5", "0", "Completed"],    # negative price
        ["T5", "01-01-2026", "A", "C", "North", "Online", "1", "100", "-1", "Completed"],  # bad discount
        ["T6", "01-01-2026", "A", "C", "North", "Online", "abc", "100", "0", "Completed"], # malformed qty
    ]
    s = make_db(rows)
    assert s["source_rows"] == 7
    assert s["rejected_rows"] == 4   # duplicate, bad date, negative qty, malformed qty
    assert s["by_category"]["missing_or_invalid_price"] == 1
    assert s["by_category"]["other_flagged"] == 1
    assert s["analytics_eligible_rows"] == 1
