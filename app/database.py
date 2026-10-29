"""SQLite access. Two kinds of connection:

* get_write_connection(): used ONLY by the import script / startup import.
* get_read_connection():  read-only (mode=ro + PRAGMA query_only) - used by
  analytics, so the question-answering path cannot modify data even by bug.
"""
import sqlite3
from contextlib import contextmanager
from pathlib import Path

from app.config import get_settings

SCHEMA = """
CREATE TABLE IF NOT EXISTS sales_transactions (
    transaction_id TEXT PRIMARY KEY,
    order_date     TEXT NOT NULL,          -- ISO YYYY-MM-DD
    product        TEXT,
    category       TEXT,
    region         TEXT,
    sales_channel  TEXT,
    quantity       INTEGER NOT NULL,
    unit_price     REAL,                   -- NULL = missing in source (never 0)
    discount_amount REAL NOT NULL DEFAULT 0,
    status         TEXT NOT NULL,          -- original status preserved
    net_revenue    REAL,                   -- (qty*price)-discount, NULL if not computable
    is_valid       INTEGER NOT NULL,       -- 1 = no data-quality problem
    is_eligible    INTEGER NOT NULL,       -- 1 = counted in analytics
    quality_flags  TEXT NOT NULL DEFAULT '',
    raw_row        TEXT NOT NULL           -- original CSV row as JSON (audit)
);
CREATE INDEX IF NOT EXISTS idx_sales_date ON sales_transactions(order_date);

CREATE TABLE IF NOT EXISTS data_quality_issues (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    import_run_id INTEGER,
    source_row INTEGER,
    transaction_id TEXT,
    issue_code TEXT NOT NULL,
    detail TEXT,
    raw_row TEXT
);

CREATE TABLE IF NOT EXISTS import_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_at TEXT NOT NULL,
    summary_json TEXT NOT NULL
);
"""


def get_write_connection(db_path: str | None = None) -> sqlite3.Connection:
    path = db_path or get_settings().db_path
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    return conn


def init_db(db_path: str | None = None) -> None:
    conn = get_write_connection(db_path)
    try:
        conn.executescript(SCHEMA)
        conn.commit()
    finally:
        conn.close()


@contextmanager
def get_read_connection(db_path: str | None = None):
    path = db_path or get_settings().db_path
    conn = sqlite3.connect(f"file:{Path(path).resolve()}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA query_only = ON")
    try:
        yield conn
    finally:
        conn.close()
