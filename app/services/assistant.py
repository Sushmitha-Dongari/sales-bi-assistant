"""Orchestrates: question -> interpret -> predefined analytics function -> template answer."""
from app.config import get_settings
from app.services import analytics
from app.services.question_interpreter import interpret


def _fmt(x) -> str:
    return f"{x:,.2f}"


def _answer(intent: str, res: dict, unit: str) -> str:
    m = res["metrics"]
    if intent == "total_revenue":
        return (f"Total net revenue is {_fmt(m['total_revenue'])} {unit} across "
                f"{m['eligible_transactions']} eligible (Completed) transactions, {m['total_quantity']} units sold.")
    if intent in ("top_product", "top_region"):
        key = "top_products" if intent == "top_product" else "top_regions"
        word = "product" if intent == "top_product" else "region"
        names = m[key]
        if not names:
            return f"There is no eligible revenue to rank {word}s."
        who = " and ".join(names)
        tie = f" (tie between {len(names)} {word}s)" if len(names) > 1 else ""
        return f"The top {word} by net revenue is {who}{tie} with {_fmt(m['top_revenue'])} {unit}."
    if intent == "monthly_trend":
        return (f"Monthly net revenue over {m['months']} months totals {_fmt(m['total_revenue'])} {unit}; "
                f"the best month was {m['best_month']}.")
    a, b, ch = m["first_month"], m["second_month"], m["absolute_change"]
    base = (f"Revenue {m['direction']} from {_fmt(m['first_revenue'])} {unit} in {a} to "
            f"{_fmt(m['second_revenue'])} {unit} in {b} (change {ch:+,.2f}")
    return base + (f", {m['percentage_change']:+.2f}%)." if m["percentage_change"] is not None
                   else "). The percentage change is undefined because the first month has zero revenue.")


def ask(question: str) -> dict:
    unit = get_settings().currency_label
    result = interpret(question)
    base = {"question": question, "interpretation_method": result.method,
            "metrics": {}, "supporting_data": [], "data_quality": {}}
    if result.intent is None:
        return {**base, "status": "unsupported", "intent": None,
                "answer": result.clarification or "Sorry, I can't answer that question."}
    i = result.intent
    if i.intent == "total_revenue":
        res = analytics.total_revenue()
    elif i.intent == "top_product":
        res = analytics.top_product()
    elif i.intent == "monthly_trend":
        res = analytics.monthly_trend()
    elif i.intent == "top_region":
        res = analytics.top_region()
    else:
        res = analytics.revenue_comparison(i.first_month, i.second_month)
    return {**base, "status": "success", "intent": i.intent, "answer": _answer(i.intent, res, unit), **res}
