"""Row validation. Pure functions - no database access.

Vocabulary (see docs/data-quality.md):
  rejected  = row NOT stored (unusable: missing/duplicate id, bad date, bad quantity)
  stored    = row saved in SQLite with raw values preserved
  valid     = stored and no data-quality issue
  eligible  = valid AND Completed AND quantity > 0  -> counted in analytics
"""
import json
import math
from dataclasses import dataclass, field
from datetime import datetime

REQUIRED_COLUMNS = [
    "Transaction_Id", "Order_date", "Product", "Category", "Region",
    "Sales_channel", "Quantity", "Unit_price", "Discount_amount", "Status",
]
# Primary category of every source row. Exactly one per row -> no double counting.
CATEGORIES = [
    "rejected", "already_present", "returned", "zero_quantity",
    "missing_or_invalid_price", "other_flagged", "eligible",
]


@dataclass
class RowResult:
    transaction_id: str | None
    stored: bool
    category: str
    record: dict | None = None
    issues: list[tuple[str, str]] = field(default_factory=list)  # (code, detail)


def _clean(v) -> str:
    return (v or "").strip()


def _num(text: str):
    """Parse a finite number, or return None."""
    try:
        x = float(text)
    except ValueError:
        return None
    return x if math.isfinite(x) else None


def validate_row(raw: dict) -> RowResult:
    tid = _clean(raw.get("Transaction_Id"))
    issues: list[tuple[str, str]] = []
    reject: list[tuple[str, str]] = []

    if not tid:
        reject.append(("missing_transaction_id", "Transaction_Id is blank"))

    # date: source format is day-month-year
    date_iso = None
    try:
        date_iso = datetime.strptime(_clean(raw.get("Order_date")), "%d-%m-%Y").date().isoformat()
    except ValueError:
        reject.append(("invalid_date", f"Order_date {raw.get('Order_date')!r} is not a valid DD-MM-YYYY date"))

    # quantity: must be a whole number; negative => rejected (cannot trust the row)
    qty = None
    q_txt = _clean(raw.get("Quantity"))
    q_num = _num(q_txt)
    if q_num is None or q_num != int(q_num):
        reject.append(("invalid_quantity", f"Quantity {q_txt!r} is not a whole number"))
    else:
        qty = int(q_num)
        if qty < 0:
            reject.append(("negative_quantity", f"Quantity {qty} is negative"))

    if reject:
        return RowResult(tid or None, False, "rejected", None, reject)

    # unit price: blank => NULL (never silently 0)
    price = None
    p_txt = _clean(raw.get("Unit_price"))
    if p_txt == "":
        issues.append(("missing_unit_price", "Unit_price is blank; stored as NULL"))
    else:
        price = _num(p_txt)
        if price is None:
            issues.append(("invalid_unit_price", f"Unit_price {p_txt!r} is not a number"))
        elif price < 0:
            issues.append(("negative_unit_price", f"Unit_price {price} is negative"))
            price = None

    # discount: blank means no discount (documented); malformed/negative/too big => flagged
    discount = 0.0
    d_txt = _clean(raw.get("Discount_amount"))
    discount_ok = True
    if d_txt != "":
        d = _num(d_txt)
        if d is None or d < 0:
            issues.append(("invalid_discount", f"Discount_amount {d_txt!r} is invalid"))
            discount_ok = False
        else:
            discount = d
    if discount_ok and price is not None and discount > qty * price:
        issues.append(("discount_exceeds_gross", "Discount is larger than quantity x unit price"))
        discount_ok = False

    status = _clean(raw.get("Status"))
    returned = status.lower() == "returned"
    if qty == 0:
        issues.append(("zero_quantity", "Quantity is 0; no sales contribution"))

    computable = price is not None and discount_ok
    net = round(qty * price - discount, 2) if computable else None
    valid = not issues  # returned/zero qty is a business state; zero qty is flagged above
    eligible = valid and status.lower() == "completed" and qty > 0

    flags = [c for c, _ in issues]
    if returned:
        flags.append("returned")

    price_issue = any(c in ("missing_unit_price", "invalid_unit_price", "negative_unit_price") for c, _ in issues)
    if returned:
        category = "returned"
    elif qty == 0:
        category = "zero_quantity"
    elif price_issue:
        category = "missing_or_invalid_price"
    elif issues:
        category = "other_flagged"
    elif eligible:
        category = "eligible"
    else:
        category = "other_flagged"  # e.g. unknown status value
        flags.append("unknown_status")
        issues.append(("unknown_status", f"Status {status!r} is not Completed/Returned"))

    record = {
        "transaction_id": tid, "order_date": date_iso,
        "product": _clean(raw.get("Product")), "category": _clean(raw.get("Category")),
        "region": _clean(raw.get("Region")), "sales_channel": _clean(raw.get("Sales_channel")),
        "quantity": qty, "unit_price": price, "discount_amount": discount,
        "status": status, "net_revenue": net,
        "is_valid": int(valid), "is_eligible": int(eligible),
        "quality_flags": ",".join(flags),
        "raw_row": json.dumps(raw, ensure_ascii=False),
    }
    return RowResult(tid, True, category, record, issues)
