import logging
import sqlite3
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.api.routes import router
from app.config import get_settings
from app.database import get_write_connection, init_db
from app.services.analytics import AnalyticsError
from app.services.ingestion import import_csv

log = logging.getLogger("bi")
APP_DIR = Path(__file__).parent
templates = Jinja2Templates(directory=str(APP_DIR / "templates"))


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Fresh checkout / fresh deploy: create tables and import the CSV if the DB is empty."""
    init_db()
    conn = get_write_connection()
    try:
        empty = conn.execute("SELECT COUNT(*) FROM sales_transactions").fetchone()[0] == 0
    finally:
        conn.close()
    if empty and Path(get_settings().csv_path).exists():
        import_csv()
    yield


app = FastAPI(title="Mini AI Business Intelligence Assistant",
              description="Ask questions about sales in plain English. Claude (optional) only interprets the "
                          "question; every number comes from predefined SQL queries on SQLite.",
              version="1.0.0", lifespan=lifespan)
app.mount("/static", StaticFiles(directory=str(APP_DIR / "static")), name="static")
app.include_router(router)


def _err(status: int, code: str, message: str) -> JSONResponse:
    return JSONResponse(status_code=status, content={"status": "error", "error": {"code": code, "message": message}})


@app.exception_handler(RequestValidationError)
async def _validation(request: Request, exc: RequestValidationError):
    msgs = "; ".join(f"{'.'.join(str(p) for p in e['loc'][1:])}: {e['msg']}" for e in exc.errors())
    return _err(422, "invalid_request", msgs or "Invalid request")


@app.exception_handler(StarletteHTTPException)
async def _http(request: Request, exc: StarletteHTTPException):
    return _err(exc.status_code, "http_error", str(exc.detail))


@app.exception_handler(AnalyticsError)
async def _analytics(request: Request, exc: AnalyticsError):
    return _err(422, "invalid_parameter", str(exc))


@app.exception_handler(sqlite3.Error)
async def _db(request: Request, exc: sqlite3.Error):
    log.error("database error: %s", type(exc).__name__)
    return _err(503, "database_error", "The database is currently unavailable. Did you run the import?")


@app.exception_handler(Exception)
async def _unexpected(request: Request, exc: Exception):
    log.exception("unexpected error")  # stack trace goes to server log only
    return _err(500, "internal_error", "Something went wrong on the server.")


@app.get("/", include_in_schema=False)
def index(request: Request):
    return templates.TemplateResponse(request, "index.html", {"currency": get_settings().currency_label})
