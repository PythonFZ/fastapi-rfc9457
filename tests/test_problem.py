import dataclasses

import pytest

from fastapi_rfc9457.models import ProblemDetail
from fastapi_rfc9457.problem import (
    _REGISTRY,
    Problem,
    ProblemError,
    _derive_type,
    extension_fields,
)


class OutOfCredit(Problem):
    """The account does not have enough credit."""

    title = "Out of Credit"
    status = 403
    balance: int
    accounts: list[str]


class PostNotFound(Problem):
    type = "/problems/tp-post-not-found"
    title = "Not Found"
    status = 404


def test_is_exception_and_holds_fields():
    err = OutOfCredit(detail="x", balance=30, accounts=["/acct/12"])
    assert isinstance(err, Exception)
    assert err.balance == 30
    assert err.accounts == ["/acct/12"]
    assert OutOfCredit.title == "Out of Credit"
    assert OutOfCredit.status == 403


def test_can_be_raised_and_chained():
    try:
        try:
            raise ValueError("root")
        except ValueError as root:
            raise OutOfCredit(balance=1, accounts=[]) from root
    except OutOfCredit as exc:
        assert isinstance(exc.__cause__, ValueError)
        assert exc.__traceback__ is not None


def test_frozen_blocks_mutation():
    err = OutOfCredit(balance=1, accounts=[])
    with pytest.raises(dataclasses.FrozenInstanceError):
        err.balance = 999


@pytest.mark.parametrize(
    "name,expected",
    [
        ("OutOfCredit", "out-of-credit"),
        ("ValidationProblem", "validation"),
        ("NotFound", "not-found"),
        ("InternalServerError", "internal-server"),
    ],
)
def test_derive_type(name, expected):
    assert _derive_type(name) == expected


def test_default_type_is_derived_kebab_id():
    assert OutOfCredit.type == "out-of-credit"


def test_explicit_type_override_is_respected():
    assert PostNotFound.type == "/problems/tp-post-not-found"


def test_registry_keyed_by_type_uri():
    assert _REGISTRY["out-of-credit"] is OutOfCredit
    assert _REGISTRY["/problems/tp-post-not-found"] is PostNotFound


def test_duplicate_type_uri_is_rejected():
    with pytest.raises(ValueError, match="Duplicate problem type"):

        class A(Problem):
            type = "dupe"
            title = "A"
            status = 400

        class B(Problem):
            type = "dupe"
            title = "B"
            status = 400


def test_extension_fields_excludes_standard_members():
    assert extension_fields(OutOfCredit) == {"balance": int, "accounts": list[str]}
    assert extension_fields(PostNotFound) == {}


def test_problem_error_wraps_a_detail():
    pd = ProblemDetail(title="Gone", status=410)
    err = ProblemError(pd)
    assert err.problem is pd
    assert "410" in str(err)
