# fastapi-rfc9457

[![PyPI](https://img.shields.io/pypi/v/fastapi-rfc9457)](https://pypi.org/project/fastapi-rfc9457/)

Typed, batteries-included [RFC 9457](https://www.rfc-editor.org/rfc/rfc9457.html)
"Problem Details for HTTP APIs" for FastAPI & Pydantic.

Define an error once - it serializes as `application/problem+json`, documents
itself in OpenAPI, and parses back into a typed exception on the client.

```python
from fastapi import FastAPI

from fastapi_rfc9457 import Problem
from fastapi_rfc9457.server import add_problem_handlers, get_problem_docs_router, problems


class OutOfCredit(Problem):
    """The account does not have enough credit."""
    title = "Out of Credit"
    status = 403
    balance: int            # typed extension members, checked at the raise site
    accounts: list[str]


class AccountSuspended(Problem):
    """The account is suspended and cannot be charged."""
    title = "Account Suspended"
    status = 403


app = FastAPI()
add_problem_handlers(app)                                          # handlers + problem+json OpenAPI
app.include_router(get_problem_docs_router(), prefix="/problems")  # dereferenceable type URIs


@app.get("/charge", responses=problems(OutOfCredit, AccountSuspended))
async def charge() -> dict:
    raise OutOfCredit(detail="Not enough credit.", balance=30, accounts=["/acct/12"])
```

## Accurate OpenAPI, for free

One route can declare several failure modes. Distinct statuses get their own
response; same-status problems become a `oneOf` union you flip through in
Swagger's **Examples** dropdown — all under `application/problem+json`.

![Swagger error responses with a problem+json examples dropdown](https://raw.githubusercontent.com/PythonFZ/fastapi-rfc9457/main/docs/img/swagger-errors.png)



## Dereferenceable `type` URIs

Mount the docs router and every problem `type` resolves to a live page listing
its typed extension members.

The `type` is derived from the docs-router mount, not hard-coded: mount at
`prefix="/problems"` and `OutOfCredit` emits and serves `/problems/out-of-credit`.
Change the prefix and bodies, OpenAPI, and doc pages move together. Set `type`
explicitly to emit a literal URI instead.

![Problem type documentation page](https://raw.githubusercontent.com/PythonFZ/fastapi-rfc9457/main/docs/img/doc-page.png)

## Typed exceptions on the client

The base install is a lean, Pydantic-only client: it parses
`application/problem+json` back into the same typed problem the server raised,
so the consumer catches `OutOfCredit`, not a status code. Wire `httpx_raise_hook`
onto an httpx client and every problem response re-raises itself:

```python
import httpx
from fastapi_rfc9457 import Problem, httpx_raise_hook


class OutOfCredit(Problem):      # the type the server declares, shared or re-stated
    title = "Out of Credit"
    status = 403
    balance: int

with httpx.Client(base_url="http://localhost:8000",
                  event_hooks={"response": [httpx_raise_hook()]}) as client:
    try:
        client.get("/charge")
    except OutOfCredit as exc:
        print(exc.balance)       # extension members round-trip back as typed attributes
```

Prefer to parse explicitly? `parse_problem(response)` returns the typed `Problem`
(or a generic `ProblemDetail` for an unknown `type`), and `raise_for_problem(response)`
raises it. Both accept an httpx/requests response, a `dict`, `bytes`, or `str`.

## Comparison with native FastAPI
see [Handling Errors](https://fastapi.tiangolo.com/tutorial/handling-errors/)

```python
class OutOfCreditError(Exception):
    def __init__(self, detail: str, balance: int) -> None:
        self.detail, self.balance = detail, balance

@app.exception_handler(OutOfCreditError)
async def _(request: Request, exc: OutOfCreditError) -> JSONResponse:
    return JSONResponse({"detail": exc.detail, "balance": exc.balance}, 403)

class OutOfCreditBody(BaseModel):
    detail: str
    balance: int

@app.get("/charge", responses={403: {"model": OutOfCreditBody}})
async def charge(token: str | None = None) -> dict:
    if token is None:
        raise HTTPException(401, "Log in first")
    raise OutOfCreditError("Not enough credit", balance=30)
```

```python
# fastapi-rfc9457 enables a single class for the exception, the body, and the OpenAPI schema
from fastapi_rfc9457 import NotAuthenticated, Problem  # NotAuthenticated ships built in
from fastapi_rfc9457.server import problems

class OutOfCredit(Problem):
    title = "Out of Credit"
    status = 403
    balance: int

@app.get("/charge", responses=problems(NotAuthenticated, OutOfCredit))
async def charge(token: str | None = None) -> dict:
    if token is None:
        raise NotAuthenticated(detail="Log in first")
    raise OutOfCredit(detail="Not enough credit", balance=30)
    # → 403 application/problem+json
    #   {"type": "/problems/out-of-credit", "title": "Out of Credit",
    #    "status": 403, "detail": "Not enough credit", "balance": 30}
```

| | Plain FastAPI | fastapi-rfc9457 |
|---|---|:---:|
| Typed extra fields in the body **and** OpenAPI | exception + handler + model, by hand | ✅ |
| Errors documented as `application/problem+json` | ❌ (`application/json`) | ✅ |
| Same-status errors as `oneOf` + Examples dropdown | ❌ | ✅ |
| Dereferenceable `type` URIs with doc pages | ❌ | ✅ |

## Similar projects

- [`fastapi-problem`](https://github.com/NRWLDev/fastapi-problem)

## Install

```bash
uv add fastapi-rfc9457[server]   # FastAPI apps: handlers, OpenAPI, docs router
uv add fastapi-rfc9457           # lean client: author + parse problems, Pydantic only
```

## Example

```bash
cd example && uv run uvicorn main:app --reload   # then open localhost:8000/docs
```

See [`example/`](./example) for the full runnable app, and
[`example/client.py`](./example/client.py) for the httpx hook (`uv add fastapi-rfc9457 httpx`)
that raises those problems back as typed exceptions on the consumer side.

## Notes

- Replaces FastAPI's default 422 body with `application/problem+json`.
