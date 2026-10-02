from collections.abc import Mapping
from typing import ClassVar

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import ValidationError

from fastapi_rfc9457 import (
    MethodNotAllowed,
    NotAuthenticated,
    NotFound,
    Problem,
    RetryAfter,
    ServiceUnavailable,
    TooManyRequests,
    UndeclaredHeaderWarning,
)
from fastapi_rfc9457.builtins import BuiltinProblems
from fastapi_rfc9457.handlers import make_handlers
from fastapi_rfc9457.openapi import problems, register_problem_components


class BasicAuthRequired(NotAuthenticated):
    """Basic credentials are required."""

    challenge = 'Basic realm="api"'


class Moved(Problem):
    """Moved elsewhere."""

    title = "Moved"
    status = 410
    location: str
    headers: ClassVar[Mapping[str, str]] = {"Location": "The new URL of the resource."}

    def response_headers(self) -> Mapping[str, str]:
        return {"Location": self.location}


def _client(*raises: Problem) -> TestClient:
    app = FastAPI()
    for exc_type, handler in make_handlers(
        strip_debug=False, instance_from_request=True, builtins=BuiltinProblems()
    ).items():
        app.add_exception_handler(exc_type, handler)
    for i, problem in enumerate(raises):
        app.get(f"/{i}")(_raiser(problem))
    return TestClient(app)


def _raiser(problem: Problem):
    def route() -> None:
        raise problem

    return route


def test_not_authenticated_sends_bearer_challenge():
    resp = _client(NotAuthenticated()).get("/0")
    assert resp.headers["www-authenticate"] == "Bearer"


def test_not_authenticated_subclass_names_its_challenge():
    resp = _client(BasicAuthRequired()).get("/0")
    assert resp.headers["www-authenticate"] == 'Basic realm="api"'


def test_custom_problem_renders_its_response_headers():
    resp = _client(Moved(location="/new")).get("/0")
    assert resp.headers["location"] == "/new"
    assert resp.json()["location"] == "/new"


def test_too_many_requests_sends_retry_after_when_set():
    resp = _client(TooManyRequests(retry_after=30)).get("/0")
    assert resp.headers["retry-after"] == "30"
    assert resp.json()["retry_after"] == 30


def test_too_many_requests_omits_retry_after_by_default():
    resp = _client(TooManyRequests()).get("/0")
    assert "retry-after" not in resp.headers
    assert "retry_after" not in resp.json()


def test_method_not_allowed_sends_allow():
    resp = _client(MethodNotAllowed(allow=["GET", "POST"])).get("/0")
    assert resp.status_code == 405
    assert resp.headers["allow"] == "GET, POST"
    assert resp.json()["allow"] == ["GET", "POST"]


def _responses(*types_: type[Problem]) -> dict:
    app = FastAPI()

    @app.get("/x", responses=problems(*types_))
    async def x() -> None: ...

    register_problem_components(app)
    return TestClient(app).get("/openapi.json").json()["paths"]["/x"]["get"]["responses"]


def test_openapi_documents_declared_headers():
    responses = _responses(NotAuthenticated, TooManyRequests, MethodNotAllowed)
    assert set(responses["401"]["headers"]) == {"WWW-Authenticate"}
    assert set(responses["429"]["headers"]) == {"Retry-After"}
    assert set(responses["405"]["headers"]) == {"Allow"}
    assert responses["401"]["headers"]["WWW-Authenticate"]["schema"] == {"type": "string"}


def test_openapi_merges_headers_of_a_shared_status():
    responses = _responses(Moved, _Gone)
    assert set(responses["410"]["headers"]) == {"Location", "Sunset"}


def test_openapi_omits_headers_for_problems_without_them():
    assert "headers" not in _responses(NotFound)["404"]


def test_openapi_documents_optional_extension_as_optional():
    app = FastAPI()

    @app.get("/x", responses=problems(TooManyRequests))
    async def x() -> None: ...

    register_problem_components(app)
    schema = TestClient(app).get("/openapi.json").json()["components"]["schemas"]["TooManyRequests"]
    assert "retry_after" not in schema.get("required", [])


class _Gone(Problem):
    """Gone for good."""

    title = "Gone"
    status = 410
    headers: ClassVar[Mapping[str, str]] = {"Sunset": "When the resource went away."}


def test_openapi_shows_the_challenge_as_header_example():
    header = _responses(NotAuthenticated)["401"]["headers"]["WWW-Authenticate"]
    assert header["example"] == "Bearer"


def test_openapi_shows_a_subclass_challenge_as_header_example():
    header = _responses(BasicAuthRequired)["401"]["headers"]["WWW-Authenticate"]
    assert header["example"] == 'Basic realm="api"'


def test_openapi_lists_each_challenge_of_a_shared_status():
    header = _responses(NotAuthenticated, BasicAuthRequired)["401"]["headers"]["WWW-Authenticate"]
    assert "example" not in header
    assert header["examples"] == {
        "NotAuthenticated": {"value": "Bearer"},
        "BasicAuthRequired": {"value": 'Basic realm="api"'},
    }


class _ForgetfulMoved(Problem):
    """Sends a header it never declared."""

    title = "Moved"
    status = 410

    def response_headers(self) -> Mapping[str, str]:
        return {"Location": "/new"}


def test_undeclared_response_header_warns_naming_class_and_header():
    with pytest.warns(UndeclaredHeaderWarning, match=r"_ForgetfulMoved.*'Location'"):
        resp = _client(_ForgetfulMoved()).get("/0")
    assert resp.headers["location"] == "/new"


def test_declared_header_matches_case_insensitively(recwarn):
    class LowerMoved(Moved):
        """Returns the declared header in lower case."""

        def response_headers(self) -> Mapping[str, str]:
            return {"location": self.location}

    _client(LowerMoved(location="/new")).get("/0")
    assert not [w for w in recwarn if issubclass(w.category, UndeclaredHeaderWarning)]


def test_service_unavailable_sends_retry_after_when_set():
    resp = _client(ServiceUnavailable(retry_after=120)).get("/0")
    assert resp.status_code == 503
    assert resp.headers["retry-after"] == "120"
    assert resp.json()["retry_after"] == 120


def test_service_unavailable_omits_retry_after_by_default():
    resp = _client(ServiceUnavailable()).get("/0")
    assert "retry-after" not in resp.headers


def test_openapi_documents_retry_after_on_503():
    assert set(_responses(ServiceUnavailable)["503"]["headers"]) == {"Retry-After"}


class _Throttled(TooManyRequests):
    """Adds a rate-limit header on top of Retry-After."""

    headers: ClassVar[Mapping[str, str]] = {"X-RateLimit-Limit": "Requests allowed per window."}

    def response_headers(self) -> Mapping[str, str]:
        return {"X-RateLimit-Limit": "100"}


def test_subclass_headers_extend_the_inherited_declaration():
    assert set(_Throttled.headers) == {"Retry-After", "X-RateLimit-Limit"}


def test_subclass_adding_a_header_sends_both_without_warning(recwarn):
    resp = _client(_Throttled(retry_after=5)).get("/0")
    assert resp.headers["retry-after"] == "5"
    assert resp.headers["x-ratelimit-limit"] == "100"
    assert not [w for w in recwarn if issubclass(w.category, UndeclaredHeaderWarning)]


def test_openapi_documents_inherited_and_added_headers():
    assert set(_responses(_Throttled)["429"]["headers"]) == {"Retry-After", "X-RateLimit-Limit"}


class _RetryThenAuth(RetryAfter, NotAuthenticated):
    """Retry-After listed first in the bases."""


class _AuthThenRetry(NotAuthenticated, RetryAfter):
    """WWW-Authenticate listed first in the bases."""


@pytest.mark.parametrize("cls", [_RetryThenAuth, _AuthThenRetry])
def test_combined_bases_send_both_headers(cls, recwarn):
    resp = _client(cls(retry_after=7)).get("/0")
    assert resp.headers["retry-after"] == "7"
    assert resp.headers["www-authenticate"] == "Bearer"
    assert not [w for w in recwarn if issubclass(w.category, UndeclaredHeaderWarning)]


@pytest.mark.parametrize("cls", [_RetryThenAuth, _AuthThenRetry])
def test_openapi_documents_both_headers_of_combined_bases(cls):
    headers = _responses(cls)["401"]["headers"]
    assert set(headers) == {"Retry-After", "WWW-Authenticate"}
    assert headers["WWW-Authenticate"]["example"] == "Bearer"


class _UndeclaredExample(Problem):
    """Gives an example for a header it never declared."""

    title = "Odd"
    status = 418

    @classmethod
    def header_examples(cls) -> Mapping[str, str]:
        return {"X-Odd": "1"}


def test_problems_rejects_an_example_for_an_undeclared_header():
    with pytest.raises(ValueError, match=r"_UndeclaredExample.*'X-Odd'"):
        problems(_UndeclaredExample)


def test_retry_after_rejects_a_negative_value():
    with pytest.raises(ValidationError):
        TooManyRequests(retry_after=-1)


class _AllowThenRetry(MethodNotAllowed, RetryAfter):
    """Allow listed first in the bases."""


def test_method_not_allowed_keeps_headers_of_later_bases():
    resp = _client(_AllowThenRetry(allow=["GET"], retry_after=3)).get("/0")
    assert resp.headers["allow"] == "GET"
    assert resp.headers["retry-after"] == "3"


class _ForgetsSuper(TooManyRequests):
    """Overrides ``response_headers`` for its own header only."""

    headers: ClassVar[Mapping[str, str]] = {"X-Shard": "The shard that throttled the request."}

    def response_headers(self) -> Mapping[str, str]:
        return {"X-Shard": "eu-1"}


def test_override_keeps_the_headers_its_bases_send():
    resp = _client(_ForgetsSuper(retry_after=4)).get("/0")
    assert resp.headers["retry-after"] == "4"
    assert resp.headers["x-shard"] == "eu-1"


class _ReChallenged(TooManyRequests):
    """Overrides the value of an inherited header."""

    def response_headers(self) -> Mapping[str, str]:
        return {"Retry-After": "60"}


def test_override_replaces_an_inherited_header_value():
    resp = _client(_ReChallenged(retry_after=4)).get("/0")
    assert resp.headers["retry-after"] == "60"


class _DigestAuth(NotAuthenticated):
    """Adds an example for its own header."""

    headers: ClassVar[Mapping[str, str]] = {"X-Realm": "The protection space."}

    @classmethod
    def header_examples(cls) -> Mapping[str, str]:
        return {"X-Realm": "api"}


def test_header_examples_keep_the_inherited_examples():
    headers = _responses(_DigestAuth)["401"]["headers"]
    assert headers["WWW-Authenticate"]["example"] == "Bearer"
    assert headers["X-Realm"]["example"] == "api"


def test_empty_headers_on_a_subclass_that_inherits_headers_raises():
    with pytest.raises(TypeError, match=r"_Silent.headers.*'Retry-After'"):

        class _Silent(TooManyRequests):
            headers: ClassVar[Mapping[str, str]] = {}
