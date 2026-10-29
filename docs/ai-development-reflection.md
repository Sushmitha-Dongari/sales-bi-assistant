# AI development reflection (editable draft)

> Replace every **[PERSONALIZE]** item with your own experience before submitting. Do not claim tools you did not use.

**AI tools used.** [PERSONALIZE] This project was generated with Claude (Claude Code–style workspace). Add any other tools you used.

**How AI assisted.** Scaffolding the structure, writing the ingestion/validation, SQL analytics, interpreter, UI, tests and docs from the challenge brief. [PERSONALIZE: what you reviewed, changed, or asked for.]

**Problems encountered (from the actual build).**
- The first message had no dataset; the CSV was supplied afterward.
- The build sandbox could not install FastAPI/httpx/Anthropic from PyPI, so the API/UI tests were written but **not executed there** (they are skipped when FastAPI is missing). [PERSONALIZE: record the result when you run `python -m pytest -q` locally.]
- Design decisions: keeping rejected vs. flagged rows distinct; exclusive summary categories; read-only DB connection for analytics.

**How problems were debugged.** [PERSONALIZE] e.g. comparing app results against an independent calculation in the tests.

**With another day.** Category/date filters; Decimal money; Claude-assisted wording (numbers locked); auth; richer fallback; CI; deployment config tests.
