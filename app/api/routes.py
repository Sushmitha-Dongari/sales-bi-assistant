import sqlite3

from fastapi import APIRouter, HTTPException

from app.schemas import AskRequest, AskResponse, ErrorResponse
from app.services import analytics, assistant
from app.config import get_settings
from app.database import get_read_connection

router = APIRouter()
ERRORS = {422: {"model": ErrorResponse}, 500: {"model": ErrorResponse}, 503: {"model": ErrorResponse}}


@router.get("/health", tags=["system"])
def health():
    try:
        with get_read_connection() as c:
            n = c.execute("SELECT COUNT(*) FROM sales_transactions").fetchone()[0]
        db = "ok"
    except sqlite3.Error:
        n, db = 0, "unavailable"
    return {"status": "ok" if db == "ok" else "degraded", "database": db, "stored_transactions": n,
            "claude_configured": get_settings().anthropic_api_key is not None}


@router.post("/api/ask", response_model=AskResponse, responses=ERRORS, tags=["assistant"],
             summary="Ask a business question in natural language")
def ask(req: AskRequest):
    return assistant.ask(req.question)


@router.get("/api/revenue/compare", tags=["analytics"], responses=ERRORS,
            summary="Compare revenue of two months (YYYY-MM)")
def compare(first_month: str, second_month: str):
    try:
        return analytics.revenue_comparison(first_month, second_month)
    except analytics.AnalyticsError as e:
        raise HTTPException(status_code=422, detail=str(e))
