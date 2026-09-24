import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from fastapi_rfc9457 import Problem, RetryAfter, ServiceUnavailable, TooManyRequests, parse_problem
from fastapi_rfc9457.integration import problem_details_lifespan
from fastapi_rfc9457.problem import iter_problem_types
from fastapi_rfc9457.server import problems


class _Base(Problem, abstract=True):
    """Shared fields, no title or status."""

    reason: str | None = None


class _Concrete(_Base):
    """A concrete child of an abstract base."""

    title = "Concrete"
    status = 418


def test_abstract_types_are_skipped_and_their_children_kept():
    types_ = set(iter_problem_types())
    assert _Base not in types_
    assert RetryAfter not in types_
    assert {_Concrete, TooManyRequests, ServiceUnavailable} <= types_


def test_children_inherit_abstract_fields():
    assert _Concrete(reason="teapot").reason == "teapot"


def test_constructing_an_abstract_type_raises():
    with pytest.raises(TypeError, match="_Base is abstract"):
        _Base()


def test_problems_rejects_an_abstract_type():
    with pytest.raises(TypeError, match="RetryAfter is abstract"):
        problems(RetryAfter)


def test_startup_check_passes_with_abstract_types_defined():
    app = FastAPI(lifespan=problem_details_lifespan)
    with TestClient(app):
        pass


def test_client_never_resolves_an_abstract_slug():
    parsed = parse_problem({"type": "/problems/retry-after", "title": "x", "status": 503})
    assert not isinstance(parsed, Problem)


def test_retry_after_types_share_the_mixin():
    assert isinstance(TooManyRequests(), RetryAfter)
    assert isinstance(ServiceUnavailable(), RetryAfter)
