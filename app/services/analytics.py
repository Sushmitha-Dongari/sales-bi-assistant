"""Analytics = predefined, parameterised SELECT queries. No SQL ever comes from users or the LLM.

Single revenue definition, applied everywhere via ELIGIBLE:
    net_revenue = quantity * unit_price - discount_amount
    counted only when is_eligible = 1  (Completed, quantity > 0, valid price/discount)
Money is stored as REAL and rounded to 2 decimals with ROUND()/round() at the output edge.
"""
import re
from datetime import date

from app.database import get_read_connection

ELIGIBLE = "is_eligible = 1"
MONTH_RE = re.compile(r"^\d{4}-(0[1-9]|1[0-2])$")


class AnalyticsError(ValueError):
    """Bad input to an analytics function (e.g. invalid month)."""


def validate_month(m: str) -> str:
    if not isinstance(m, str) or not MONTH_RE.match(m):
        raise AnalyticsError(f"Invalid month {m!r}: expected YYYY-MM with month 01-12")
    return m


def _next_month_start(m: str) -> str:
    y, mo = int(m[:4]), int(m[5:])
    return date(y + (mo == 12), mo % 12 + 1, 1).isoformat()


def _quality(conn) -> dict:
    row = conn.execute(
        """SELECT COUNT(*) AS stored,
                  SUM(is_eligible) AS eligible,
                  SUM(CASE WHEN lower(status)='returned' THEN 1 ELSE 0 END) AS returned,
                  SUM(CASE WHEN quantity=0 THEN 1 ELSE 0 END) AS zero_quantity,
                  SUM(CASE WHEN unit_price IS NULL THEN 1 ELSE 0 END) AS missing_price
           FROM sales_transactions"""
    ).fetchone()
    rejected = conn.execute(
        "SELECT COUNT(DISTINCT source_row) FROM data_quality_issues WHERE issue_code IN "
        "('missing_transaction_id','invalid_date','invalid_quantity','negative_quantity','duplicate_transaction_id')"
    ).fetchone()[0]
    d = {k: (row[k] or 0) for k in row.keys()}
    d["rejected_rows"] = rejected
    d["excluded_from_analytics"] = d["stored"] - d["eligible"]
    d["note"] = (
        "Only Completed transactions with quantity > 0 and a valid unit price count. "
        "Excluded: returned, zero-quantity and missing-price rows."
    )
    return d


def _r(x) -> float:
    return round(x or 0, 2)


def total_revenue() -> dict:
    with get_read_connection() as c:
        r = c.execute(
            f"SELECT COALESCE(SUM(net_revenue),0) rev, COUNT(*) n, COALESCE(SUM(quantity),0) qty "
            f"FROM sales_transactions WHERE {ELIGIBLE}"
        ).fetchone()
        return {
            "metrics": {"total_revenue": _r(r["rev"]), "eligible_transactions": r["n"], "total_quantity": r["qty"],
                        "definition": "Sum of (quantity x unit_price - discount) over Completed, valid transactions."},
            "supporting_data": [],
            "data_quality": _quality(c),
        }


def _group_top(column: str, label: str) -> dict:
    # `column` is chosen from our own code (never user input) - see the two callers below.
    with get_read_connection() as c:
        rows = c.execute(
            f"""SELECT {column} AS name, ROUND(SUM(net_revenue),2) AS revenue,
                       SUM(quantity) AS quantity, COUNT(*) AS transactions
                FROM sales_transactions WHERE {ELIGIBLE}
                GROUP BY {column} ORDER BY revenue DESC, name ASC"""
        ).fetchall()
        data = [dict(r) for r in rows]
        top = max((r["revenue"] for r in data), default=None)
        winners = [r["name"] for r in data if r["revenue"] == top]  # all ties kept
        return {
            "metrics": {f"top_{label}s": winners, "top_revenue": top, "is_tie": len(winners) > 1,
                        "ranking_metric": "net revenue (not units sold)"},
            "supporting_data": data,
            "data_quality": _quality(c),
        }


def top_product() -> dict:
    return _group_top("product", "product")


def top_region() -> dict:
    return _group_top("region", "region")


def monthly_trend() -> dict:
    with get_read_connection() as c:
        rows = c.execute(
            f"""SELECT strftime('%Y-%m', order_date) AS month, ROUND(SUM(net_revenue),2) AS revenue,
                       COUNT(*) AS transactions, SUM(quantity) AS quantity
                FROM sales_transactions WHERE {ELIGIBLE} GROUP BY month ORDER BY month"""
        ).fetchall()
        span = c.execute("SELECT MIN(order_date), MAX(order_date) FROM sales_transactions").fetchone()
        have = {r["month"]: dict(r) for r in rows}
        data = []
        if span[0]:
            y, m = int(span[0][:4]), int(span[0][5:7])
            ey, em = int(span[1][:4]), int(span[1][5:7])
            while (y, m) <= (ey, em):  # fill months without eligible revenue with 0
                key = f"{y:04d}-{m:02d}"
                data.append(have.get(key, {"month": key, "revenue": 0.0, "transactions": 0, "quantity": 0}))
                y, m = (y + 1, 1) if m == 12 else (y, m + 1)
        best = max(data, key=lambda r: r["revenue"], default=None)
        return {
            "metrics": {"months": len(data), "total_revenue": _r(sum(r["revenue"] for r in data)),
                        "best_month": best["month"] if best else None,
                        "empty_month_policy": "Months in the data period with no eligible sales are shown with 0."},
            "supporting_data": data,
            "data_quality": _quality(c),
        }


def _month_totals(c, month: str) -> dict:
    r = c.execute(
        f"""SELECT COALESCE(ROUND(SUM(net_revenue),2),0) AS revenue, COUNT(*) AS transactions
            FROM sales_transactions WHERE {ELIGIBLE} AND order_date >= ? AND order_date < ?""",
        (month + "-01", _next_month_start(month)),
    ).fetchone()
    return {"month": month, "revenue": r["revenue"], "transactions": r["transactions"]}


def revenue_comparison(first_month: str, second_month: str) -> dict:
    validate_month(first_month)
    validate_month(second_month)
    with get_read_connection() as c:
        a, b = _month_totals(c, first_month), _month_totals(c, second_month)
        change = round(b["revenue"] - a["revenue"], 2)
        pct = round(change / a["revenue"] * 100, 2) if a["revenue"] else None
        direction = "increased" if change > 0 else "decreased" if change < 0 else "unchanged"
        return {
            "metrics": {
                "first_month": first_month, "first_revenue": a["revenue"],
                "second_month": second_month, "second_revenue": b["revenue"],
                "absolute_change": change, "percentage_change": pct, "direction": direction,
                "percentage_note": None if pct is not None else
                    "Percentage change is undefined because the first month's revenue is zero.",
            },
            "supporting_data": [a, b],
            "data_quality": _quality(c),
        }
