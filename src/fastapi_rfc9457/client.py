"""Client-side parsing of ``application/problem+json`` back into typed problems."""

from __future__ import annotations

import json
from typing import Any

from .models import PROBLEM_MEDIA_TYPE, ProblemDetail
from .problem import Problem, ProblemError, extension_fields, iter_problem_types


def _coerce(source: Any) -> dict[str, Any]:
    if isinstance(source, dict):
        return source
    if isinstance(source, (bytes, bytearray, str)):
        return json.loads(source)
    if hasattr(source, "json"):  # httpx.Response / requests.Response
        return source.json()
    raise TypeError(f"Cannot parse a problem from {type(source)!r}")


def parse_problem(source: Any) -> ProblemDetail | Problem:
    """Parse a problem document into a typed ``Problem`` or generic ``ProblemDetail``.

    Parameters
    ----------
    source : Any
        A response object (with ``.json()``), a ``dict``, ``bytes``, or ``str``.

    Returns
    -------
    ProblemDetail | Problem
        The registered ``Problem`` subclass (extension members restored typed)
        when ``type`` is known, otherwise a generic ``ProblemDetail``.
    """
    detail = ProblemDetail.model_validate(_coerce(source))
    cls = next((c for c in iter_problem_types() if c.type == detail.type), None)
    if cls is None:
        return detail
    extensions = {
        name: getattr(detail, name) for name in extension_fields(cls) if hasattr(detail, name)
    }
    return cls(detail=detail.detail, instance=detail.instance, **extensions)  # type: ignore[call-arg]


def _content_type(response: Any) -> str:
    headers = getattr(response, "headers", {})
    return headers.get("content-type", "") if hasattr(headers, "get") else ""


def raise_for_problem(response: Any) -> None:
    """Raise the mapped ``Problem`` / ``ProblemError`` if this is a problem response.

    Parameters
    ----------
    response : Any
        A response object with ``.headers`` and ``.json()``.
    """
    if PROBLEM_MEDIA_TYPE not in _content_type(response):
        return
    parsed = parse_problem(response)
    if isinstance(parsed, Problem):
        raise parsed
    raise ProblemError(parsed)


def httpx_raise_hook():
    """Return an httpx ``response`` event hook that auto-raises on problem responses.

    Returns
    -------
    Callable
        Use as ``httpx.Client(event_hooks={"response": [httpx_raise_hook()]})``.
    """

    def hook(response: Any) -> None:
        if PROBLEM_MEDIA_TYPE in _content_type(response):
            if hasattr(response, "read"):
                response.read()
            raise_for_problem(response)

    return hook
