"""This file MUST type-check clean — it is part of the main pyright run."""

from collections.abc import Mapping
from typing import assert_type

from fastapi_rfc9457 import MethodNotAllowed, NotAuthenticated, Problem, TooManyRequests


class OutOfCredit(Problem):
    """The account does not have enough credit."""

    title = "Out of Credit"
    status = 403
    balance: int
    accounts: list[str]


err = OutOfCredit(detail="x", balance=30, accounts=["/acct/12"])
assert_type(err.balance, int)
assert_type(err.accounts, list[str])


class BasicAuthRequired(NotAuthenticated):
    """Basic credentials are required."""

    challenge = 'Basic realm="api"'


assert_type(TooManyRequests(retry_after=30).retry_after, int | None)
assert_type(MethodNotAllowed(allow=["GET"]).allow, list[str])
assert_type(BasicAuthRequired().response_headers(), Mapping[str, str])
