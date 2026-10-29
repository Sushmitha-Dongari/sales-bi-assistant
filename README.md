# Mini AI Business Intelligence Assistant

Ask sales questions in plain English. **Claude (optional) or a rule-based fallback only interprets the question into one of 5 fixed intents; every number comes from predefined, parameterised SQL on SQLite.**

## Features
- 5 analytics: total revenue, top product, monthly trend, top region, month-vs-month comparison
- Idempotent CSV import with a data-quality audit trail (51 source rows, nothing silently dropped)
- Claude interpretation with strict Pydantic validation, timeout, and rule-based fallback (response says which was used)
- Read-only analytics connection; no SQL ever comes from users or the LLM
- Web UI (served by FastAPI, Chart.js charts), OpenAPI docs at `/docs`
- pytest suite (no internet / API key needed)

## Stack
Python 3.11+, FastAPI, SQLite (`sqlite3`), Pydantic v2, Anthropic SDK (optional), python-dotenv, Jinja2, vanilla JS + Chart.js (CDN), pytest.

## Setup
```bash
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env               # optional: add ANTHROPIC_API_KEY
```
CSV: already at `data/sales.csv` (51 rows). The DB (`data/sales.db`) is created on first start.

## Import data (explicit, idempotent)
```bash
python -m scripts.import_data
```
Prints a summary. Running it again reports `already_present_rows: 51` and adds nothing. (The server also auto-imports on startup if the DB is empty.)

## Run
```bash
uvicorn app.main:app --reload
```
UI: http://127.0.0.1:8000 · API docs: http://127.0.0.1:8000/docs

## Tests
```bash
python -m pytest -q
```

## API
`GET /health` → `{"status":"ok","database":"ok","stored_transactions":51,"claude_configured":false}`

`POST /api/ask`
```json
{ "question": "Compare February and March 2026" }
```
```json
{
  "question": "Compare February and March 2026",
  "status": "success",
  "intent": "revenue_comparison",
  "answer": "Revenue decreased from 234,600.00 currency units in 2026-02 to 223,900.00 ... (change -10,700.00, -4.56%).",
  "metrics": {"first_month": "2026-02", "first_revenue": 234600.0, "second_month": "2026-03", "second_revenue": 223900.0,
              "absolute_change": -10700.0, "percentage_change": -4.56, "direction": "decreased", "percentage_note": null},
  "supporting_data": [{"month": "2026-02", "revenue": 234600.0, "transactions": 8}, {"month": "2026-03", "revenue": 223900.0, "transactions": 8}],
  "data_quality": {"stored": 51, "eligible": 48, "returned": 1, "zero_quantity": 1, "missing_price": 1, "rejected_rows": 0},
  "interpretation_method": "rule_based"
}
```
`status` is `success` or `unsupported` (HTTP 200, with a helpful message). Errors use one schema:
`{"status":"error","error":{"code":"invalid_request","message":"..."}}` (422 bad input, 503 DB unavailable, 500 unexpected – no stack traces).

`GET /api/revenue/compare?first_month=2026-02&second_month=2026-03` – same analytics, direct (422 on invalid month).

## Revenue definition
`net_revenue = quantity × unit_price − discount_amount`, only for **eligible** rows. Money is stored as REAL and rounded to 2 decimals; the dataset has no currency, so values are labelled "currency units" (`CURRENCY_LABEL`). Percentage change = `(second − first) / first × 100`; if first = 0 it is `null` with an explanation.

## Data-quality rules (details: docs/data-quality.md)
| Case | Handling |
|---|---|
| Returned (TXN0033) | stored, flagged, excluded |
| Zero quantity (TXN0034) | stored, flagged, excluded |
| Missing price (TXN0051) | stored with NULL price (never 0), flagged, excluded |
| Duplicate id / bad date / negative or malformed quantity | **rejected** (not stored), recorded in `data_quality_issues` |
| Negative price / bad or oversized discount | stored, flagged, excluded |

Imported result for the supplied file: 51 source rows → 48 eligible, 1 returned, 1 zero-quantity, 1 missing-price, 0 rejected.

## AI design & why it limits hallucination
Claude gets the question and must return JSON `{intent, first_month, second_month}`. Pydantic rejects unknown intents/fields and bad months. The intent maps to a fixed Python function. Claude never sees data and never produces numbers or SQL; answers are deterministic templates filled from DB results. If Claude fails/times out (no retries) or returns bad JSON, the rule-based fallback is tried; if it can't confidently interpret, the user is asked to rephrase.

## Security controls
Parameterised SQL; no user/LLM-supplied SQL; read-only connection (`mode=ro` + `query_only`); strict request schema (max 300 chars); API key only from env, never logged or sent to the browser; generic error messages; `textContent` (no HTML injection) in the UI.

## Known limitations
- Only the 5 fixed question types; no category/date filters (not implemented, so never silently ignored – such questions are asked to be rephrased).
- Rule-based fallback is keyword-based; unusual phrasing may be "unsupported". Month names without a year assume 2026.
- SQLite file: fine for this dataset, not for heavy concurrent writes.
- Float money; fine here, use Decimal/integer minor units for real accounting once currency is known.
- No authentication.

## Troubleshooting
- `database_error` / empty answers: run `python -m scripts.import_data`.
- `ModuleNotFoundError: app`: run commands from the project root.
- Fallback used though key set: check `/health` → `claude_configured`; timeouts/auth errors are logged (without the key).

## Deploy (free, e.g. Render)
Push to GitHub → Render "New Web Service" (or "Blueprint" using `render.yaml`) → start command `uvicorn app.main:app --host 0.0.0.0 --port $PORT`. Optionally set `ANTHROPIC_API_KEY`. The DB is rebuilt from `data/sales.csv` at startup.

## Git
```bash
git init && git add . && git commit -m "Mini AI BI assistant"
git branch -M main
git remote add origin https://github.com/<you>/sales-bi-assistant.git
git push -u origin main
```
