# fastapi-rfc9457 — example app

```bash
uv run uvicorn main:app --reload   # open http://localhost:8000/docs
```

```bash
curl -i localhost:8000/posts/999          # 404  application/problem+json
curl -i "localhost:8000/search?limit=abc" # 422  errors[] with loc ["query","limit"]
curl -i localhost:8000/charge             # 401  NotAuthenticated (no token)
curl -i "localhost:8000/charge?token=x"   # 403  OutOfCredit + typed balance/accounts
curl -s localhost:8000/problems/out-of-credit  # dereferenced type-doc page
```

`/charge` declares three problems via `problems(...)`: a 401 and a same-status
403 `oneOf` union (`OutOfCredit` / `AccountSuspended`) — see them in `/docs`.

## Consuming it with the httpx hook

`fastapi-rfc9457[client]` ships an httpx event hook that turns every
`application/problem+json` reply back into the same typed exception the server
raised. [`client.py`](./client.py) is a runnable consumer of the server above.

With the demo server running (above), in another shell from this `example/`
directory:

```bash
uv add fastapi-rfc9457[client]   # the httpx extra
uv run client.py                 # connects to http://localhost:8000
```

It prints:

```text
GET /posts/1   -> {'id': '1', 'title': 'Hello'}
PostNotFound   -> Post 999 not found
OutOfCredit    -> balance=30, accounts=['/accounts/12']
NotAuthenticated -> Log in to charge this account.
```

The hook is synchronous (`response.read()`), so it wires onto `httpx.Client`;
`httpx.AsyncClient` is not supported today.

## Notes

- This replaces FastAPI's default 422 `application/json` body with
  `application/problem+json` carrying a structured `errors[]` extension member —
  intended, since the goal is a uniform error surface.
- Under `app.debug=True`, Starlette renders a traceback page *instead of*
  invoking the 500 handler, so the `problem+json` 500 path isn't exercised in
  debug; Starlette also re-raises the unhandled exception after the handler runs
  (for logging). Both are expected.
