import pytest

pytest.importorskip("fastapi")
pytest.importorskip("httpx")
from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402


@pytest.fixture
def client(db):
    with TestClient(app) as c:
        yield c


def test_health(client):
    r = client.get("/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok" and body["stored_transactions"] == 51
    assert "path" not in str(body).lower() and "key" not in body


def test_ask_success_schema(client):
    r = client.post("/api/ask", json={"question": "Which product generated the highest revenue?"})
    assert r.status_code == 200
    b = r.json()
    assert set(b) == {"question", "status", "intent", "answer", "metrics", "supporting_data",
                      "data_quality", "interpretation_method"}
    assert b["status"] == "success" and b["intent"] == "top_product" and b["interpretation_method"] == "rule_based"


def test_ask_unsupported(client):
    b = client.post("/api/ask", json={"question": "What's the weather?"}).json()
    assert b["status"] == "unsupported"


@pytest.mark.parametrize("payload", [{"question": ""}, {"question": "   "}, {}, {"question": "x" * 1000}])
def test_ask_rejects_bad_requests(client, payload):
    r = client.post("/api/ask", json=payload)
    assert r.status_code == 422 and r.json()["status"] == "error"


def test_ask_invalid_json(client):
    r = client.post("/api/ask", content="{not json", headers={"content-type": "application/json"})
    assert r.status_code == 422 and r.json()["error"]["code"] == "invalid_request"


def test_compare_endpoint_invalid_month(client):
    r = client.get("/api/revenue/compare", params={"first_month": "2026-13", "second_month": "2026-02"})
    assert r.status_code == 422 and r.json()["status"] == "error"


def test_index_page(client):
    assert "Mini AI Business Intelligence Assistant" in client.get("/").text
