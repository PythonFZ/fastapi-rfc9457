"""Ready-to-use built-in problem types and the structured-validation types."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, ClassVar

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
    headers: ClassVar[Mapping[str, str]] = {
        "WWW-Authenticate": "The challenge(s) the client must answer to authenticate "
        "(RFC 9110 §11.6.1)."
    }
    #: The ``WWW-Authenticate`` challenge, e.g. ``'Basic realm="api"'`` in a subclass.
    challenge: ClassVar[str] = "Bearer"

    def response_headers(self) -> Mapping[str, str]:
        """Send the class's ``challenge`` as ``WWW-Authenticate``."""
        return {"WWW-Authenticate": self.challenge}

    @classmethod
    def header_examples(cls) -> Mapping[str, str]:
        """Document the class's ``challenge`` as the ``WWW-Authenticate`` example."""
        return {"WWW-Authenticate": cls.challenge}


class Forbidden(Problem):
    """You do not have permission to access this resource."""

    title = "Forbidden"
    status = 403


class NotFound(Problem):
    """The requested resource was not found."""

    title = "Not Found"
    status = 404


class MethodNotAllowed(Problem):
    """The request method is not supported by the target resource."""

    title = "Method Not Allowed"
    status = 405
    headers: ClassVar[Mapping[str, str]] = {
        "Allow": "The methods the target resource supports (RFC 9110 §10.2.1)."
    }
    allow: list[str]

    def response_headers(self) -> Mapping[str, str]:
        """Send ``allow`` as the ``Allow`` header."""
        return {"Allow": ", ".join(self.allow)}


class Conflict(Problem):
    """The request conflicts with the current state of the resource."""

    title = "Conflict"
    status = 409


class UnprocessableContent(Problem):
    """The request was well-formed but could not be processed."""

    title = "Unprocessable Content"
    status = 422


class RetryAfter(Problem, abstract=True):
    """Base for problems that tell the client when to retry (RFC 9110 §10.2.3)."""

    headers: ClassVar[Mapping[str, str]] = {
        "Retry-After": "Seconds to wait before retrying (RFC 9110 §10.2.3)."
    }
    #: Seconds the client waits before retrying; sent as ``Retry-After`` when set.
    retry_after: int | None = None

    def response_headers(self) -> Mapping[str, str]:
        """Add ``retry_after`` as ``Retry-After`` when set."""
        headers = dict(super().response_headers())
        if self.retry_after is not None:
            headers["Retry-After"] = str(self.retry_after)
        return headers


class TooManyRequests(RetryAfter):
    """You have sent too many requests in a given amount of time."""

    title = "Too Many Requests"
    status = 429


class InternalServerError(Problem):
    """The server encountered an unexpected condition."""

    title = "Internal Server Error"
    status = 500


class ServiceUnavailable(RetryAfter):
    """The server is temporarily unable to handle the request."""

    title = "Service Unavailable"
    status = 503


class InvalidParam(BaseModel):
    """One field-level validation failure (RFC 9457 extension member).

    Attributes
    ----------
    loc : list[str | int]
        Faithful FastAPI location, e.g. ``["body", 0, "task_name"]`` — the list
        index is preserved (why we use ``loc`` rather than RFC 7807's ``name``).
        We deliberately omit a JSON Pointer rendering: ``loc`` already carries
        strictly more (it keeps int indices distinct from string keys and avoids
        the ``/``-escaping ambiguity a flat pointer would introduce), and a
        location-class-prefixed pointer like ``/query/limit`` does not point into
        any real request document.
    detail : str
        The pydantic error message.
    type : str
        The pydantic error code, e.g. ``"missing"``.
    input : Any
        The offending value; populated only when ``strip_debug`` is False.
    """

    loc: list[str | int]
    detail: str
    type: str
    input: Any = None


class ValidationProblem(Problem):
    """The request failed validation."""

    # `type` is intentionally not pinned: it derives to the "validation" slug and
    # is resolved against the mounted docs route at emit time (see uris.py).
    title = "Unprocessable Content"
    status = 422
    errors: list[InvalidParam]
