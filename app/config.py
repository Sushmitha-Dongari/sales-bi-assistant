"""Settings are read from environment variables (and an optional .env file).

They are read through get_settings() at call time (not import time) so tests
can point the app at a temporary database with monkeypatch.setenv.
"""
import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()
BASE_DIR = Path(__file__).resolve().parent.parent


@dataclass(frozen=True)
class Settings:
    db_path: str
    csv_path: str
    anthropic_api_key: str | None
    anthropic_model: str
    ai_timeout_seconds: float
    currency_label: str
    max_question_length: int = 300


def get_settings() -> Settings:
    return Settings(
        db_path=os.getenv("SALES_DB_PATH", str(BASE_DIR / "data" / "sales.db")),
        csv_path=os.getenv("SALES_CSV_PATH", str(BASE_DIR / "data" / "sales.csv")),
        anthropic_api_key=(os.getenv("ANTHROPIC_API_KEY") or "").strip() or None,
        anthropic_model=os.getenv("ANTHROPIC_MODEL", "claude-haiku-5-5"),
        ai_timeout_seconds=float(os.getenv("AI_TIMEOUT_SECONDS", "10")),
        # The dataset gives no currency, so we show neutral "currency units".
        currency_label=os.getenv("CURRENCY_LABEL", "currency units"),
    )
