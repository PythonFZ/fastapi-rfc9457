"""The emitted ``type`` URI is resolved from the mounted docs route (issue #6).

A problem's ``type`` no longer hard-codes its directory: it is computed from
wherever the docs router is actually mounted, so renaming the mount prefix moves
the response bodies, the OpenAPI consts, and the doc pages together. The slug is
the stable identity; the prefix is deployment configuration.
"""

from typing import Annotated

from fastapi import FastAPI, Query
from fastapi.testclient import TestClient

from fastapi_rfc9457.client import parse_problem
from fastapi_rfc9457.docs import get_problem_docs_router
from fastapi_rfc9457.integration import add_problem_handlers
from fastapi_rfc9457.models import ProblemDetail
from fastapi_rfc9457.openapi import problems
from fastapi_rfc9457.problem import Problem


class ResOutOfCredit(Problem):
    """The account does not have enough credit."""

    title = "Out of Credit"
    status = 403
    balance: int


class VerbatimAbsolute(Problem):
    """An explicit absolute `type` is emitted exactly as written."""

    type = "/static/errors/teapot"
    title = "Teapot"
    status = 418


class VerbatimBare(Problem):
    """An explicit bare `type` is emitted exactly as written — no prefixing."""

    type = "just-this"
    title = "Bare"
    status = 400


def _app(prefix: str) -> FastAPI:
    """An app whose docs router is mounted at ``prefix`` (route-derived mode)."""
    app = FastAPI()
    add_problem_handlers(app)
    app.include_router(get_problem_docs_router(), prefix=prefix)

    @app.get("/charge", responses=problems(ResOutOfCredit))
    async def charge() -> dict:
        raise ResOutOfCredit(detail="no", balance=1)

    @app.get("/search")
    async def search(limit: Annotated[int, Query(ge=1)] = 10) -> dict:
        return {"limit": limit}

    return app


def test_wire_type_tracks_custom_docs_prefix():
    body = TestClient(_app("/v1/problems")).get("/charge").json()
    assert body["type"] == "/v1/problems/res-out-of-credit"


def test_validation_type_tracks_custom_docs_prefix():
    body = TestClient(_app("/v1/problems")).get("/search?limit=abc").json()
    assert body["type"] == "/v1/problems/validation"


def test_openapi_const_and_example_track_custom_docs_prefix():
    doc = TestClient(_app("/v1/problems")).get("/openapi.json").json()
    props = doc["components"]["schemas"]["ResOutOfCredit"]["properties"]
    assert props["type"]["const"] == "/v1/problems/res-out-of-credit"


def test_explicit_type_emitted_verbatim_ignoring_mount():
    # Written type is THE type URI: emitted exactly, never reprefixed by the mount.
    app = FastAPI()
    add_problem_handlers(app)
    app.include_router(get_problem_docs_router(), prefix="/v2/problems")

    @app.get("/t", responses=problems(VerbatimAbsolute))
    async def teapot() -> dict:
        raise VerbatimAbsolute(detail="no")

    @app.get("/b", responses=problems(VerbatimBare))
    async def bare() -> dict:
        raise VerbatimBare(detail="no")

    client = TestClient(app)
    assert client.get("/t").json()["type"] == "/static/errors/teapot"
    assert client.get("/b").json()["type"] == "just-this"


def test_explicit_type_const_emitted_verbatim_in_openapi():
    app = FastAPI()
    add_problem_handlers(app)
    app.include_router(get_problem_docs_router(), prefix="/v2/problems")

    @app.get("/t", responses=problems(VerbatimAbsolute))
    async def teapot() -> dict:
        raise VerbatimAbsolute(detail="no")

    doc = TestClient(app).get("/openapi.json").json()
    const = doc["components"]["schemas"]["VerbatimAbsolute"]["properties"]["type"]["const"]
    assert const == "/static/errors/teapot"


def test_type_falls_back_to_declared_slug_when_docs_not_mounted():
    app = FastAPI()
    add_problem_handlers(app)

    @app.get("/charge", responses=problems(ResOutOfCredit))
    async def charge() -> dict:
        raise ResOutOfCredit(detail="no", balance=1)

    body = TestClient(app).get("/charge").json()
    # No docs router: a valid RFC 9457 relative reference, just not dereferenceable.
    assert body["type"] == "res-out-of-credit"


def test_client_matches_type_by_slug_regardless_of_prefix():
    # Server emitted a deep, prefixed URI; the client only knows the slug identity.
    body = {
        "type": "/deep/v9/res-out-of-credit",
        "title": "Out of Credit",
        "status": 403,
        "balance": 7,
    }
    parsed = parse_problem(body)
    assert isinstance(parsed, ResOutOfCredit)
    assert parsed.balance == 7


def test_doc_page_reports_the_url_it_lives_at():
    client = TestClient(_app("/v1/problems"))
    body = client.get(
        "/v1/problems/res-out-of-credit", headers={"accept": "application/json"}
    ).json()
    assert body["type"] == "/v1/problems/res-out-of-credit"


def test_wire_type_round_trips_back_to_typed_problem():
    client = TestClient(_app("/v1/problems"))
    raw = client.get("/charge").json()
    parsed = parse_problem(raw)
    assert isinstance(parsed, ResOutOfCredit)
    assert ProblemDetail.model_validate(raw).type == "/v1/problems/res-out-of-credit"
