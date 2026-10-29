import pytest

from app.services import analytics as an


def expected(source_rows):
    """Independent pure-Python calculation straight from the CSV."""
    out = []
    for r in source_rows:
        if r["Status"] != "Completed" or int(r["Quantity"]) == 0 or r["Unit_price"] == "":
            continue
        rev = int(r["Quantity"]) * float(r["Unit_price"]) - float(r["Discount_amount"])
        d, m, y = r["Order_date"].split("-")
        out.append((r["Product"], r["Region"], f"{y}-{m}", rev))
    return out


def test_total_revenue(db, source_rows):
    res = an.total_revenue()
    exp = expected(source_rows)
    assert res["metrics"]["total_revenue"] == round(sum(e[3] for e in exp), 2)
    assert res["metrics"]["eligible_transactions"] == 48
    dq = res["data_quality"]
    assert (dq["returned"], dq["zero_quantity"], dq["missing_price"]) == (1, 1, 1)


def test_top_product_and_breakdown_verify(db, source_rows):
    res = an.top_product()
    by = {}
    for p, _, _, rev in expected(source_rows):
        by[p] = by.get(p, 0) + rev
    assert res["metrics"]["top_products"] == [max(by, key=by.get)]
    assert {r["name"]: r["revenue"] for r in res["supporting_data"]} == {k: round(v, 2) for k, v in by.items()}


def test_top_region(db, source_rows):
    by = {}
    for _, reg, _, rev in expected(source_rows):
        by[reg] = by.get(reg, 0) + rev
    assert an.top_region()["metrics"]["top_regions"] == [max(by, key=by.get)]


def test_monthly_trend_chronological_and_complete(db, source_rows):
    res = an.monthly_trend()
    months = [r["month"] for r in res["supporting_data"]]
    assert months == ["2026-01", "2026-02", "2026-03", "2026-04", "2026-05", "2026-06"]
    by = {}
    for _, _, m, rev in expected(source_rows):
        by[m] = by.get(m, 0) + rev
    assert {r["month"]: r["revenue"] for r in res["supporting_data"]} == {k: round(v, 2) for k, v in by.items()}


def test_comparison_change_and_percentage(db):
    m = an.revenue_comparison("2026-02", "2026-03")["metrics"]
    assert m["absolute_change"] == round(m["second_revenue"] - m["first_revenue"], 2)
    assert m["percentage_change"] == round(m["absolute_change"] / m["first_revenue"] * 100, 2)
    assert m["direction"] in ("increased", "decreased")


def test_comparison_zero_first_month_gives_null_percentage(db):
    m = an.revenue_comparison("2026-07", "2026-01")["metrics"]   # July has no data
    assert m["first_revenue"] == 0
    assert m["percentage_change"] is None and "undefined" in m["percentage_note"]
    assert m["direction"] == "increased"


@pytest.mark.parametrize("bad", ["2026-13", "2026-1", "26-01", "2026/01", "2026-00", "'; DROP TABLE x;--"])
def test_invalid_month_rejected(db, bad):
    with pytest.raises(an.AnalyticsError):
        an.revenue_comparison(bad, "2026-01")


def test_ties_return_all_winners(make_db):
    make_db([
        ["T1", "01-01-2026", "Alpha", "C", "North", "Online", "1", "100", "0", "Completed"],
        ["T2", "02-01-2026", "Beta", "C", "South", "Online", "1", "100", "0", "Completed"],
        ["T3", "03-01-2026", "Gamma", "C", "South", "Online", "1", "50", "0", "Completed"],
    ])
    assert an.top_product()["metrics"]["top_products"] == ["Alpha", "Beta"]
    assert an.top_product()["metrics"]["is_tie"] is True
    assert an.top_region()["metrics"]["top_regions"] == ["South"]  # 150 vs 100


def test_analytics_connection_is_read_only(db):
    import sqlite3
    from app.database import get_read_connection
    with get_read_connection() as c:
        with pytest.raises(sqlite3.OperationalError):
            c.execute("DELETE FROM sales_transactions")
