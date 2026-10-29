"""CSV -> SQLite import. Idempotent: re-running never duplicates transactions."""
import csv
import json
from datetime import datetime, timezone

from app.config import get_settings
from app.database import get_write_connection, init_db
from app.services.data_quality import CATEGORIES, REQUIRED_COLUMNS, validate_row


def import_csv(csv_path: str | None = None, db_path: str | None = None) -> dict:
    settings = get_settings()
    csv_path = csv_path or settings.csv_path
    init_db(db_path)
    conn = get_write_connection(db_path)
    counts = {c: 0 for c in CATEGORIES}
    total = 0
    try:
        with open(csv_path, newline="", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            missing = [c for c in REQUIRED_COLUMNS if c not in (reader.fieldnames or [])]
            if missing:
                raise ValueError(f"CSV is missing required columns: {missing}")
            run_id = conn.execute(
                "INSERT INTO import_runs(run_at, summary_json) VALUES (?, '{}')",
                (datetime.now(timezone.utc).isoformat(),),
            ).lastrowid
            seen_in_file: set[str] = set()
            # One transaction: the whole import commits together or not at all.
            for row_no, raw in enumerate(reader, start=2):  # row 1 = header
                if not any((v or "").strip() for v in raw.values()):
                    continue  # skip fully blank lines
                total += 1
                res = validate_row(raw)
                issues = list(res.issues)
                category = res.category

                if res.stored:
                    tid = res.transaction_id
                    if tid in seen_in_file:
                        category, res.stored = "rejected", False
                        issues = [("duplicate_transaction_id", f"{tid} appears more than once in the file")]
                    else:
                        seen_in_file.add(tid)
                        exists = conn.execute(
                            "SELECT 1 FROM sales_transactions WHERE transaction_id=?", (tid,)
                        ).fetchone()
                        if exists:
                            category = "already_present"  # re-import: skipped, not duplicated
                            res.stored = False
                            issues = []

                if res.stored:
                    r = res.record
                    conn.execute(
                        """INSERT INTO sales_transactions(transaction_id, order_date, product, category,
                           region, sales_channel, quantity, unit_price, discount_amount, status,
                           net_revenue, is_valid, is_eligible, quality_flags, raw_row)
                           VALUES (:transaction_id,:order_date,:product,:category,:region,:sales_channel,
                           :quantity,:unit_price,:discount_amount,:status,:net_revenue,:is_valid,
                           :is_eligible,:quality_flags,:raw_row)""", r)
                counts[category] += 1
                for code, detail in issues:
                    conn.execute(
                        """INSERT INTO data_quality_issues(import_run_id, source_row, transaction_id,
                           issue_code, detail, raw_row) VALUES (?,?,?,?,?,?)""",
                        (run_id, row_no, res.transaction_id, code, detail, json.dumps(raw)),
                    )
            summary = _summary(total, counts)
            conn.execute("UPDATE import_runs SET summary_json=? WHERE id=?", (json.dumps(summary), run_id))
            conn.commit()
            return summary
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def _summary(total: int, counts: dict) -> dict:
    stored_new = total - counts["rejected"] - counts["already_present"]
    return {
        "source_rows": total,
        "rejected_rows": counts["rejected"],
        "already_present_rows": counts["already_present"],
        "stored_new_rows": stored_new,
        "by_category": counts,  # mutually exclusive; sums to source_rows
        "analytics_eligible_rows": counts["eligible"],
        "flagged_rows": counts["returned"] + counts["zero_quantity"]
        + counts["missing_or_invalid_price"] + counts["other_flagged"],
    }
