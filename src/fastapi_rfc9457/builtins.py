"""Ready-to-use built-in problem types and the structured-validation types."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel

from .problem import Problem


class BadRequest(Problem):
    """The request was malformed."""

    title = "Bad Request"
    status = 400


class NotAuthenticated(Problem):
    """Authentication is required and has failed or not been provided."""

    title = "Unauthorized"
    status = 401


class Forbidden(Problem):
    """You do not have permission to access this resource."""

    title = "Forbidden"
    status = 403


class NotFound(Problem):
    """The requested resource was not found."""

    title = "Not Found"
    status = 404


class Conflict(Problem):
    """The request conflicts with the current state of the resource."""

    title = "Conflict"
    status = 409


class UnprocessableContent(Problem):
    """The request was well-formed but could not be processed."""

    title = "Unprocessable Content"
    status = 422


class TooManyRequests(Problem):
    """You have sent too many requests in a given amount of time."""

    title = "Too Many Requests"
    status = 429


class InternalServerError(Problem):
    """The server encountered an unexpected condition."""

    title = "Internal Server Error"
    status = 500


class InvalidParam(BaseModel):
    """One field-level validation failure (RFC 9457 extension member).

    Attributes
    ----------
    loc : list[str | int]
        Faithful FastAPI location, e.g. ``["body", 0, "task_name"]`` — the list
        index is preserved (why we use ``loc`` rather than RFC 7807's ``name``).
    pointer : str | None
        RFC 6901 JSON Pointer convenience, e.g. ``"/body/0/task_name"``.
    detail : str
        The pydantic error message.
    type : str
        The pydantic error code, e.g. ``"missing"``.
    input : Any
        The offending value; populated only when ``strip_debug`` is False.
    """

    loc: list[str | int]
    pointer: str | None = None
    detail: str
    type: str
    input: Any = None


class ValidationProblem(Problem):
    """The request failed validation."""

    type = "/problems/validation"
    title = "Unprocessable Content"
    status = 422
    errors: list[InvalidParam]
