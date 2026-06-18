"""This file MUST produce specific pyright errors.

It is EXCLUDED from the main pyright run (see pyproject [tool.pyright].exclude)
and checked instead by tests/test_static_typing.py.
"""

from fastapi_rfc9457 import Problem


class OutOfCredit(Problem):
    title = "Out of Credit"
    status = 403
    balance: int
    accounts: list[str]


OutOfCredit(detail="x")  # reportCallIssue: missing balance, accounts
OutOfCredit(balance="lots", accounts=[])  # reportArgumentType: balance is int


class BadStatus(Problem):
    title = "x"
    status = "nope"  # reportAssignmentType: status is int
