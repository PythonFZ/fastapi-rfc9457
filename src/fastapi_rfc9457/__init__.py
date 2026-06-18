"""fastapi-rfc9457 — typed RFC 9457 Problem Details for FastAPI & Pydantic v2."""

from __future__ import annotations

from importlib.metadata import PackageNotFoundError, version

from .builtins import (
    BadRequest,
    Conflict,
    Forbidden,
    InternalServerError,
    InvalidParam,
    NotAuthenticated,
    NotFound,
    TooManyRequests,
    UnprocessableContent,
    ValidationProblem,
)
from .client import httpx_raise_hook, parse_problem, raise_for_problem
from .docs import get_problem_docs_router
from .integration import add_problem_handlers, problem_details_lifespan
from .models import PROBLEM_MEDIA_TYPE, ProblemDetail
from .openapi import problems
from .problem import Problem, ProblemError

try:
    __version__ = version("fastapi-rfc9457")
except PackageNotFoundError:  # pragma: no cover
    __version__ = "0.0.0"

__all__ = [
    "PROBLEM_MEDIA_TYPE",
    "BadRequest",
    "Conflict",
    "Forbidden",
    "InternalServerError",
    "InvalidParam",
    "NotAuthenticated",
    "NotFound",
    "Problem",
    "ProblemDetail",
    "ProblemError",
    "TooManyRequests",
    "UnprocessableContent",
    "ValidationProblem",
    "__version__",
    "add_problem_handlers",
    "get_problem_docs_router",
    "httpx_raise_hook",
    "parse_problem",
    "problem_details_lifespan",
    "problems",
    "raise_for_problem",
]
