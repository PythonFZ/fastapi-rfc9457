import dataclasses

import pydantic
import pytest

from fastapi_rfc9457.models import ProblemDetail
from fastapi_rfc9457.problem import (
    Problem,
    ProblemError,
    _derive_type,
    extension_fields,
    iter_problem_types,
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


def test_unknown_kwarg_is_rejected_not_swallowed():
    # `status` (like `title`/`type`) is a ClassVar constant, not a field. A caller
    # who writes `OutOfCredit(status=404, ...)` believes they are overriding the
    # status; silently dropping it would ship a 403 while the author thinks it's a
    # 404. Required fields are supplied here so the *only* fault is the stray kwarg.
    with pytest.raises(pydantic.ValidationError) as exc_info:
        OutOfCredit(status=404, balance=30, accounts=[])
    assert "status" in str(exc_info.value)


def test_misspelled_extension_field_is_rejected():
    # All real fields are supplied, so a missing-required error cannot mask the
    # fault: a typo'd extra member (`balnce`) must itself fail loudly rather than
    # being silently dropped.
    with pytest.raises(pydantic.ValidationError) as exc_info:
        OutOfCredit(balance=30, accounts=[], balnce=99)
    assert "balnce" in str(exc_info.value)


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


def test_iter_problem_types_discovers_defined_subclasses():
    discovered = set(iter_problem_types())
    assert OutOfCredit in discovered
    assert PostNotFound in discovered


def test_duplicate_type_uri_does_not_raise_at_definition_time():
    # Duplicates are deferred to OpenAPI build time (see test_openapi), so merely
    # defining two same-URI types must not raise on import.
    class DefDupeA(Problem):
        type = "/problems/def-dupe"
        title = "A"
        status = 400

    class DefDupeB(Problem):
        type = "/problems/def-dupe"
        title = "B"
        status = 400

    assert DefDupeA.type == DefDupeB.type == "/problems/def-dupe"


def test_extension_fields_excludes_standard_members():
    assert extension_fields(OutOfCredit) == {"balance": int, "accounts": list[str]}
    assert extension_fields(PostNotFound) == {}


def test_problem_error_wraps_a_detail():
    pd = ProblemDetail(title="Gone", status=410)
    err = ProblemError(pd)
    assert err.problem is pd
    assert "410" in str(err)
