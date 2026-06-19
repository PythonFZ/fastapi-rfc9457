"""Regression tests for issue #9.

A ``Problem`` raised through (or behind) a FastAPI ``yield`` dependency must keep
its status, type and payload. FastAPI unwinds ``yield`` dependencies through an
``AsyncExitStack``; ``contextlib`` reassigns ``exc.__traceback__`` at the Python
level on the way out. While ``Problem`` was a frozen dataclass that assignment
raised ``FrozenInstanceError``, masking the problem as a generic 500.
"""

from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

from fastapi_rfc9457 import add_problem_handlers
from fastapi_rfc9457.models import PROBLEM_MEDIA_TYPE, ProblemDetail
from fastapi_rfc9457.problem import Problem


class PostNotFound(Problem):
    type = "/problems/yd-post-not-found"
    title = "Not Found"
    status = 404


class OutOfCredit(Problem):
    type = "/problems/yd-out-of-credit"
    title = "Out of Credit"
    status = 403
    balance: int
    accounts: list[str]


class Escalated(Problem):
    type = "/problems/yd-escalated"
    title = "Conflict"
    status = 409


async def _yield_dep():
    yield 1


def test_problem_through_yield_dependency_keeps_status_not_500():
    app = FastAPI()
    add_problem_handlers(app)

    @app.get("/guarded")
    async def guarded(_=Depends(_yield_dep)):
        raise PostNotFound(detail="missing")

    client = TestClient(app, raise_server_exceptions=False)
    r = client.get("/guarded")
    assert r.status_code == 404
    assert r.headers["content-type"] == PROBLEM_MEDIA_TYPE
    body = ProblemDetail.model_validate(r.json())
    assert body.status == 404
    assert body.type == "/problems/yd-post-not-found"
    assert body.detail == "missing"


def test_problem_through_nested_yield_deps_loses_no_extension_fields():
    # The exception unwinds through several AsyncExitStack frames; every field
    # (detail, instance, and the typed extension members) must survive intact.
    app = FastAPI()
    add_problem_handlers(app)

    @app.get("/charge")
    async def charge(
        _a=Depends(_yield_dep),
        _b=Depends(_yield_dep),
        _c=Depends(_yield_dep),
    ):
        raise OutOfCredit(detail="no credit", balance=30, accounts=["/acct/12"])

    client = TestClient(app, raise_server_exceptions=False)
    r = client.get("/charge")
    assert r.status_code == 403
    body = ProblemDetail.model_validate(r.json())
    assert body.status == 403
    assert body.detail == "no credit"
    assert body.instance == "/charge"
    dumped = body.model_dump()
    assert dumped["balance"] == 30
    assert dumped["accounts"] == ["/acct/12"]


def test_reraised_as_different_problem_type_through_yield_dep_uses_new_type():
    # Catch one problem and escalate to a different problem type from inside a
    # yield-guarded route. The (now extended) traceback must be escalated to the
    # currently-raised problem, so the response reflects the NEW type/status.
    app = FastAPI()
    add_problem_handlers(app)

    @app.get("/escalate")
    async def escalate(_=Depends(_yield_dep)):
        try:
            raise PostNotFound(detail="orig")
        except PostNotFound as exc:
            raise Escalated(detail="escalated") from exc

    client = TestClient(app, raise_server_exceptions=False)
    r = client.get("/escalate")
    assert r.status_code == 409
    body = ProblemDetail.model_validate(r.json())
    assert body.type == "/problems/yd-escalated"
    assert body.status == 409
    assert body.detail == "escalated"
