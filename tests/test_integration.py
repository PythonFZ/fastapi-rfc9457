import warnings

from fastapi import FastAPI
from fastapi.testclient import TestClient

from fastapi_rfc9457.integration import add_problem_handlers
from fastapi_rfc9457.models import PROBLEM_MEDIA_TYPE, ProblemDetail
from fastapi_rfc9457.openapi import problems
from fastapi_rfc9457.problem import Problem


class PostNotFound(Problem):
    """The requested post does not exist."""

    type = "/problems/integration/post-not-found"
    title = "Not Found"
    status = 404


# A single shared, module-level constant reused across requests.
POST_NOT_FOUND = PostNotFound()


def build_app() -> FastAPI:
    app = FastAPI()
    add_problem_handlers(app)

    @app.get("/posts/{post_id}", responses=problems(PostNotFound))
    async def get_post(post_id: str) -> dict:
        raise POST_NOT_FOUND

    return app


def test_one_call_wires_handlers_and_openapi():
    client = TestClient(build_app())
    r = client.get("/posts/9")
    assert r.status_code == 404
    assert r.headers["content-type"] == PROBLEM_MEDIA_TYPE

    doc = client.get("/openapi.json").json()
    assert "PostNotFound" in doc["components"]["schemas"]
    assert "ProblemDetail" in doc["components"]["schemas"]


def test_state_safety_shared_problem_across_paths():
    """Each request gets its own resolved `instance`."""
    client = TestClient(build_app())
    a = ProblemDetail.model_validate(client.get("/posts/aaa").json())
    b = ProblemDetail.model_validate(client.get("/posts/bbb").json())
    assert a.instance == "/posts/aaa"
    assert b.instance == "/posts/bbb"
    # the shared constant was never mutated:
    assert POST_NOT_FOUND.instance is None


def test_idempotent_second_call_warns():
    app = FastAPI()
    add_problem_handlers(app)
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        add_problem_handlers(app)
    assert any("more than once" in str(w.message) for w in caught)
