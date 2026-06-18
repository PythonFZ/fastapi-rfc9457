"""This file MUST type-check clean — it is part of the main pyright run."""

from typing import assert_type

from fastapi_rfc9457 import Problem


class OutOfCredit(Problem):
    """The account does not have enough credit."""

    title = "Out of Credit"
    status = 403
    balance: int
    accounts: list[str]


err = OutOfCredit(detail="x", balance=30, accounts=["/acct/12"])
assert_type(err.balance, int)
assert_type(err.accounts, list[str])
