# fastapi-rfc9457 — example app

```bash
uv run uvicorn example.main:app --reload

curl -i localhost:8000/posts/999          # 404  application/problem+json
curl -i "localhost:8000/search?limit=abc" # 422  errors[] with loc ["query","limit"]
curl -i localhost:8000/charge             # 403  OutOfCredit + typed balance/accounts
curl -s localhost:8000/problems/out-of-credit  # dereferenced type-doc page
curl -s localhost:8000/openapi.json | jq '.components.schemas | keys'  # ProblemDetail + types
```

## Migration notes

- This replaces FastAPI's default 422 `application/json` body with
  `application/problem+json` carrying a structured `errors[]` extension member —
  intended, since the goal is a uniform error surface.
- Under `app.debug=True`, Starlette renders a traceback page *instead of*
  invoking the 500 handler, so the `problem+json` 500 path isn't exercised in
  debug; Starlette also re-raises the unhandled exception after the handler runs
  (for logging). Both are expected.
