import csv
import shutil
from pathlib import Path

import pytest

from app.services.ingestion import import_csv

ROOT = Path(__file__).resolve().parent.parent
HEADER = ["Transaction_Id", "Order_date", "Product", "Category", "Region", "Sales_channel",
          "Quantity", "Unit_price", "Discount_amount", "Status"]


@pytest.fixture
def db(tmp_path, monkeypatch):
    """Isolated temp DB with the real 51-row dataset imported."""
    monkeypatch.setenv("SALES_DB_PATH", str(tmp_path / "test.db"))
    monkeypatch.setenv("SALES_CSV_PATH", str(ROOT / "data" / "sales.csv"))
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    import_csv()
    return tmp_path / "test.db"


@pytest.fixture
def make_db(tmp_path, monkeypatch):
    """Factory: build a DB from a list of row lists (HEADER order)."""
    def _make(rows):
        p = tmp_path / "custom.csv"
        with open(p, "w", newline="") as f:
            w = csv.writer(f)
            w.writerow(HEADER)
            w.writerows(rows)
        monkeypatch.setenv("SALES_DB_PATH", str(tmp_path / "custom.db"))
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        return import_csv(str(p))
    return _make


@pytest.fixture
def source_rows():
    with open(ROOT / "data" / "sales.csv", newline="") as f:
        return list(csv.DictReader(f))
