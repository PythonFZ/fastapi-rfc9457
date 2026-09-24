"""This file MUST produce specific pyright errors.

It is EXCLUDED from the main pyright run (see pyproject [tool.pyright].exclude)
and checked instead by tests/test_static_typing.py.
"""

from fastapi import FastAPI

from fastapi_rfc9457 import MethodNotAllowed, NotAuthenticated, Problem, ValidationProblem
from fastapi_rfc9457.server import add_problem_handlers


class OutOfCredit(Problem):
    title = "Out of Credit"
    status = 403
    balance: int
    accounts: list[str]


OutOfCredit(detail="x")  # reportCallIssue: missing balance, accounts
OutOfCredit(balance="lots", accounts=[])  # reportArgumentType: balance is int
OutOfCredit(status=404)  # status can not be set dynamically.


class BadStatus(Problem):
    title = "x"
    status = "nope"  # reportAssignmentType: status is int


MethodNotAllowed()  # reportCallIssue: missing allow
NotAuthenticated(headers={"X": "y"})  # reportCallIssue: headers is a ClassVar


add_problem_handlers(FastAPI(), validation=OutOfCredit)  # named-builtin: reportArgumentType
add_problem_handlers(FastAPI(), internal=ValidationProblem)  # named-builtin: reportArgumentType
