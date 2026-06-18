# fastapi-rfc9457 — working agreement

- Python is managed with **uv**. Use `uv run …`, `uv add …`, `uv sync`. Never `pip`.
- Run pre-commit with **`uvx prek --all-files`** (not `pre-commit`).
- TDD: write the failing test first; keep commits small.
- Docstrings: **numpy style**.
- Two test tiers: runtime (`TestClient`) and static (`tests/static/` via pyright).
- Never weaken a typing guarantee to make pyright pass — fix the cause.
