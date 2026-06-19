from fastapi import APIRouter, FastAPI
from fastapi.testclient import TestClient

from fastapi_rfc9457.docs import get_problem_docs_router
from fastapi_rfc9457.integration import add_problem_handlers
from fastapi_rfc9457.openapi import problems
from fastapi_rfc9457.problem import Problem


class DocOutOfCredit(Problem):
    """The account does not have enough credit."""

    type = "/problems/doc-out-of-credit"
    title = "Out of Credit"
    status = 403
    balance: int


def _explicit_app() -> FastAPI:
    app = FastAPI()
    app.include_router(
        get_problem_docs_router(DocOutOfCredit), prefix="/problems", tags=["problems"]
    )
    return app


def _route_derived_app() -> FastAPI:
    """No explicit type list: the docs router follows the routes."""
    app = FastAPI()
    add_problem_handlers(app)
    app.include_router(get_problem_docs_router(), prefix="/problems", tags=["problems"])

    @app.get("/charge", responses=problems(DocOutOfCredit))
    async def charge() -> dict:
        raise DocOutOfCredit(detail="no", balance=1)

    return app


def test_explicit_json_doc_page():
    client = TestClient(_explicit_app())
    r = client.get("/problems/doc-out-of-credit", headers={"accept": "application/json"})
    assert r.status_code == 200
    body = r.json()
    assert body["type"] == "/problems/doc-out-of-credit"
    assert body["title"] == "Out of Credit"
    assert body["status"] == 403
    assert "enough credit" in body["description"]
    assert "balance" in body["extensions"]


def test_explicit_html_doc_page():
    client = TestClient(_explicit_app())
    r = client.get("/problems/doc-out-of-credit", headers={"accept": "text/html"})
    assert r.status_code == 200
    assert "text/html" in r.headers["content-type"]
    assert "Out of Credit" in r.text


def test_route_derived_serves_pages_for_types_used_on_routes():
    client = TestClient(_route_derived_app())
    r = client.get("/problems/doc-out-of-credit", headers={"accept": "application/json"})
    assert r.status_code == 200
    assert r.json()["title"] == "Out of Credit"


def test_route_derived_serves_always_on_validation_type():
    # ValidationProblem is emitted by every app's 422 handler, so its page resolves
    # without being declared on any route.
    client = TestClient(_route_derived_app())
    assert client.get("/problems/validation").status_code == 200


def test_route_derived_unknown_slug_is_404():
    client = TestClient(_route_derived_app())
    assert client.get("/problems/not-a-real-type").status_code == 404


def test_extension_member_types_render_readable_names():
    # The doc page returns a plain JSON dict (no Pydantic response model), so we
    # index it directly. `balance: int` must show as "int", not "<class 'int'>".
    client = TestClient(_explicit_app())
    r = client.get("/problems/doc-out-of-credit", headers={"accept": "application/json"})
    assert r.status_code == 200
    assert r.json()["extensions"]["balance"] == "int"


def test_html_doc_page_escapes_and_shows_member_types():
    client = TestClient(_explicit_app())
    r = client.get("/problems/doc-out-of-credit", headers={"accept": "text/html"})
    assert r.status_code == 200
    # "<class 'int'>" would be swallowed by the browser as a bogus tag.
    assert "<class" not in r.text
    assert "<code>balance</code>: int" in r.text


def test_empty_explicit_falls_back_to_route_derived():
    # Calling with no args is the route-derived mode, not an error.
    router = get_problem_docs_router()
    assert any(getattr(r, "name", "") == "problem-doc" for r in router.routes)


def _route_derived_included_app() -> FastAPI:
    """Problem-raising route mounted via include_router rather than on the app.

    FastAPI >= 0.137 nests included routes under an _IncludedRouter wrapper, so
    the type must still be discovered for its doc page to resolve (issue #10).
    """
    app = FastAPI()
    add_problem_handlers(app)
    app.include_router(get_problem_docs_router(), prefix="/problems", tags=["problems"])

    router = APIRouter()

    @router.get("/charge", responses=problems(DocOutOfCredit))
    async def charge() -> dict:
        raise DocOutOfCredit(detail="no", balance=1)

    app.include_router(router, prefix="/api")
    return app


def test_route_derived_serves_pages_for_types_on_included_router():
    client = TestClient(_route_derived_included_app())
    r = client.get("/problems/doc-out-of-credit", headers={"accept": "application/json"})
    assert r.status_code == 200
    assert r.json()["title"] == "Out of Credit"
