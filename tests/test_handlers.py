from typing import Annotated

from fastapi import FastAPI, HTTPException, Query
from fastapi.testclient import TestClient
from pydantic import BaseModel

from fastapi_rfc9457.handlers import make_handlers
from fastapi_rfc9457.models import PROBLEM_MEDIA_TYPE
from fastapi_rfc9457.problem import Problem


class OutOfCredit(Problem):
    """Not enough credit."""

    type = "/problems/out-of-credit"
    title = "Out of Credit"
    status = 403
    balance: int
    accounts: list[str]


class Item(BaseModel):
    task_name: str


def build_app(*, strip_debug=False, instance_from_request=True) -> FastAPI:
    app = FastAPI()
    for exc_type, handler in make_handlers(
        strip_debug=strip_debug, instance_from_request=instance_from_request
    ).items():
        app.add_exception_handler(exc_type, handler)

    @app.get("/charge")
    async def charge() -> dict:
        raise OutOfCredit(detail="no credit", balance=30, accounts=["/acct/12"])

    @app.get("/search")
    async def search(limit: Annotated[int, Query(ge=1, le=100)] = 10) -> dict:
        return {"limit": limit}

    @app.post("/items")
    async def items(payload: list[Item]) -> dict:
        return {"n": len(payload)}

    @app.get("/missing")
    async def missing() -> dict:
        raise HTTPException(status_code=404, detail="nope")

    @app.get("/boom")
    async def boom() -> dict:
        raise RuntimeError("kaboom")

    @app.get("/needs-auth")
    async def needs_auth() -> dict:
        raise HTTPException(
            status_code=401, detail="auth required", headers={"WWW-Authenticate": "Bearer"}
        )

    return app


def test_problem_handler_emits_typed_problem_json():
    client = TestClient(build_app())
    r = client.get("/charge")
    assert r.status_code == 403
    assert r.headers["content-type"] == PROBLEM_MEDIA_TYPE
    body = r.json()
    assert body["type"] == "/problems/out-of-credit"
    assert body["title"] == "Out of Credit"
    assert body["balance"] == 30
    assert body["accounts"] == ["/acct/12"]
    assert body["instance"] == "/charge"


def test_validation_handler_query_param():
    client = TestClient(build_app())
    r = client.get("/search?limit=abc")
    assert r.status_code == 422
    assert r.headers["content-type"] == PROBLEM_MEDIA_TYPE
    body = r.json()
    assert body["type"] == "/problems/validation"
    assert body["status"] == 422
    assert body["errors"][0]["loc"] == ["query", "limit"]
    assert body["errors"][0]["type"] == "int_parsing"


def test_validation_handler_preserves_list_index_no_flattening():
    """Regression guard: a multi-error list body keeps per-item loc/field/type."""
    client = TestClient(build_app())
    r = client.post("/items", json=[{}, {"task_name": "ok"}, {}])
    assert r.status_code == 422
    body = r.json()
    locs = sorted(e["loc"] for e in body["errors"])
    assert locs == [["body", 0, "task_name"], ["body", 2, "task_name"]]
    for e in body["errors"]:
        assert e["type"] == "missing"
        assert e["pointer"] in ("/body/0/task_name", "/body/2/task_name")


def test_validation_input_gated_by_strip_debug():
    client_dbg = TestClient(build_app(strip_debug=False))
    body = client_dbg.get("/search?limit=abc").json()
    assert "input" in body["errors"][0]

    client_prod = TestClient(build_app(strip_debug=True))
    body = client_prod.get("/search?limit=abc").json()
    assert "input" not in body["errors"][0]


def test_http_handler_intercepts_http_exception():
    client = TestClient(build_app())
    r = client.get("/missing")
    assert r.status_code == 404
    assert r.headers["content-type"] == PROBLEM_MEDIA_TYPE
    body = r.json()
    assert body["title"] == "Not Found"
    assert body["detail"] == "nope"
    assert body["instance"] == "/missing"


def test_unhandled_handler_returns_500():
    client = TestClient(build_app(strip_debug=False), raise_server_exceptions=False)
    r = client.get("/boom")
    assert r.status_code == 500
    assert r.headers["content-type"] == PROBLEM_MEDIA_TYPE
    body = r.json()
    assert body["title"] == "Internal Server Error"
    assert "RuntimeError" in body["detail"]


def test_unhandled_handler_strip_debug_redacts_detail():
    client = TestClient(build_app(strip_debug=True), raise_server_exceptions=False)
    body = client.get("/boom").json()
    assert body["status"] == 500
    assert body.get("detail") is None


def test_instance_from_request_false_omits_instance():
    client = TestClient(build_app(instance_from_request=False))
    body = client.get("/charge").json()
    assert "instance" not in body


def test_http_handler_forwards_exception_headers():
    client = TestClient(build_app())
    r = client.get("/needs-auth")
    assert r.status_code == 401
    assert r.headers["content-type"] == PROBLEM_MEDIA_TYPE
    assert r.headers["WWW-Authenticate"] == "Bearer"
