from typing import Annotated

from fastapi import FastAPI, HTTPException, Query
from fastapi.testclient import TestClient
from pydantic import BaseModel

from fastapi_rfc9457.handlers import make_handlers
from fastapi_rfc9457.models import PROBLEM_MEDIA_TYPE, ProblemDetail
from fastapi_rfc9457.problem import Problem


class OutOfCredit(Problem):
    """Not enough credit."""

    type = "/problems/th-out-of-credit"
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
    # Validate the whole RFC 9457 envelope through the wire model, then assert.
    problem = ProblemDetail.model_validate(r.json())
    assert problem.type == "/problems/th-out-of-credit"
    assert problem.title == "Out of Credit"
    assert problem.status == 403
    assert problem.instance == "/charge"
    extras = problem.model_dump()
    assert extras["balance"] == 30
    assert extras["accounts"] == ["/acct/12"]


def test_validation_handler_query_param():
    client = TestClient(build_app())
    r = client.get("/search?limit=abc")
    assert r.status_code == 422
    assert r.headers["content-type"] == PROBLEM_MEDIA_TYPE
    problem = ProblemDetail.model_validate(r.json())
    assert problem.type == "/problems/validation"
    assert problem.status == 422
    errors = problem.model_dump()["errors"]
    assert errors[0]["loc"] == ["query", "limit"]
    assert errors[0]["type"] == "int_parsing"


def test_validation_handler_preserves_list_index_no_flattening():
    """Regression guard: a multi-error list body keeps per-item loc/field/type."""
    client = TestClient(build_app())
    r = client.post("/items", json=[{}, {"task_name": "ok"}, {}])
    assert r.status_code == 422
    errors = ProblemDetail.model_validate(r.json()).model_dump()["errors"]
    locs = sorted(e["loc"] for e in errors)
    assert locs == [["body", 0, "task_name"], ["body", 2, "task_name"]]
    for e in errors:
        assert e["type"] == "missing"
        assert "pointer" not in e


def test_validation_input_gated_by_strip_debug():
    # Wire-level presence of the per-error `input` key (serialization behavior),
    # so this asserts on the raw body rather than through the model.
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
    problem = ProblemDetail.model_validate(r.json())
    assert problem.title == "Not Found"
    assert problem.detail == "nope"
    assert problem.instance == "/missing"


def test_unhandled_handler_returns_500():
    client = TestClient(build_app(strip_debug=False), raise_server_exceptions=False)
    r = client.get("/boom")
    assert r.status_code == 500
    assert r.headers["content-type"] == PROBLEM_MEDIA_TYPE
    problem = ProblemDetail.model_validate(r.json())
    assert problem.title == "Internal Server Error"
    assert problem.detail is not None and "RuntimeError" in problem.detail


def test_unhandled_handler_strip_debug_redacts_detail():
    client = TestClient(build_app(strip_debug=True), raise_server_exceptions=False)
    problem = ProblemDetail.model_validate(client.get("/boom").json())
    assert problem.status == 500
    assert problem.detail is None


def test_instance_from_request_false_omits_instance():
    # `instance` is dropped from the wire when unset (exclude_none), which the
    # model can't observe (absent vs. null both parse to None) — assert on the body.
    client = TestClient(build_app(instance_from_request=False))
    assert "instance" not in client.get("/charge").json()


def test_http_handler_forwards_exception_headers():
    client = TestClient(build_app())
    r = client.get("/needs-auth")
    assert r.status_code == 401
    assert r.headers["content-type"] == PROBLEM_MEDIA_TYPE
    assert r.headers["WWW-Authenticate"] == "Bearer"
