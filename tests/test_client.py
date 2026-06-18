import json

import pytest

from fastapi_rfc9457.client import httpx_raise_hook, parse_problem, raise_for_problem
from fastapi_rfc9457.models import PROBLEM_MEDIA_TYPE, ProblemDetail
from fastapi_rfc9457.problem import Problem, ProblemError


class ClientOutOfCredit(Problem):
    """Not enough credit."""

    type = "/problems/client-out-of-credit"
    title = "Out of Credit"
    status = 403
    balance: int
    accounts: list[str]


_REGISTERED_BODY = {
    "type": "/problems/client-out-of-credit",
    "title": "Out of Credit",
    "status": 403,
    "detail": "no",
    "balance": 30,
    "accounts": ["/acct/12"],
}
_UNKNOWN_BODY = {"type": "urn:unknown", "title": "Mystery", "status": 418, "teapot": True}


class FakeResponse:
    def __init__(self, body: dict, *, problem: bool = True):
        self._body = body
        self.headers = {"content-type": PROBLEM_MEDIA_TYPE if problem else "application/json"}

    def json(self):
        return self._body

    def read(self):
        return json.dumps(self._body).encode()


def test_parse_registered_type_returns_typed_instance():
    parsed = parse_problem(FakeResponse(_REGISTERED_BODY))
    assert isinstance(parsed, ClientOutOfCredit)
    assert parsed.balance == 30
    assert parsed.accounts == ["/acct/12"]
    assert parsed.detail == "no"


def test_parse_unknown_type_returns_generic_detail():
    parsed = parse_problem(FakeResponse(_UNKNOWN_BODY))
    assert isinstance(parsed, ProblemDetail)
    assert parsed.model_dump()["teapot"] is True


def test_parse_accepts_dict_and_bytes():
    assert isinstance(parse_problem(_UNKNOWN_BODY), ProblemDetail)
    assert isinstance(parse_problem(json.dumps(_UNKNOWN_BODY).encode()), ProblemDetail)


def test_raise_for_problem_registered_raises_typed():
    with pytest.raises(ClientOutOfCredit):
        raise_for_problem(FakeResponse(_REGISTERED_BODY))


def test_raise_for_problem_unknown_raises_problem_error():
    with pytest.raises(ProblemError):
        raise_for_problem(FakeResponse(_UNKNOWN_BODY))


def test_raise_for_problem_non_problem_response_is_noop():
    raise_for_problem(FakeResponse({"ok": True}, problem=False))  # no raise


def test_httpx_hook_raises_on_problem_response():
    hook = httpx_raise_hook()
    with pytest.raises(ClientOutOfCredit):
        hook(FakeResponse(_REGISTERED_BODY))
