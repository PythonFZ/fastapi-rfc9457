# fastapi-rfc9457

Typed, batteries-included [RFC 9457](https://www.rfc-editor.org/rfc/rfc9457.html)
"Problem Details for HTTP APIs" for the latest FastAPI & Pydantic v2.

```python
from fastapi import FastAPI
from fastapi_rfc9457 import add_problem_handlers, get_problem_docs_router, Problem, problems


class OutOfCredit(Problem):
    """The account does not have enough credit."""
    type = "/problems/out-of-credit"
    title = "Out of Credit"
    status = 403
    balance: int                  # typed extension members, checked at the raise site
    accounts: list[str]


app = FastAPI()
add_problem_handlers(app)                                       # handlers + OpenAPI
app.include_router(get_problem_docs_router(), prefix="/problems")  # dereferenceable type URIs


@app.get("/charge", responses=problems(OutOfCredit))
async def charge() -> dict:
    raise OutOfCredit(detail="Not enough credit.", balance=30, accounts=["/acct/12"])
```

Every error — your problems, `RequestValidationError`, `HTTPException`, and
unhandled exceptions — is emitted as `application/problem+json`.

## Why this one

- **Typed + validated extension members** that round-trip through serialization,
  OpenAPI, and the client.
- **Accurate per-route OpenAPI** under `application/problem+json`.
- **Structured 422** that preserves field + list-index mapping (no flattening).
- **Client-side parsing** back into typed problems.

## Install

```bash
uv add fastapi-rfc9457          # add fastapi-rfc9457[client] for the httpx hook
```

## Example

See [`example/`](./example) — `uv run uvicorn example.main:app --reload`.

## Notes

- Replaces FastAPI's default 422 body with `application/problem+json` (intended).
- Under `app.debug=True`, Starlette shows a traceback page instead of the 500
  handler, and re-raises unhandled exceptions after the handler (for logging).
