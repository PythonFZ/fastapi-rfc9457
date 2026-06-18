"""The four exception handlers and the per-request wire-model builder."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from http import HTTPStatus
from typing import cast

from fastapi import Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.responses import Response

from .builtins import InternalServerError, InvalidParam, ValidationProblem
from .models import PROBLEM_MEDIA_TYPE, ProblemDetail
from .problem import Problem, extension_fields
from .uris import resolve_type_uri

Handler = Callable[[Request, Exception], Awaitable[Response]]


def build_wire(problem: Problem, *, instance: str | None, type_uri: str) -> ProblemDetail:
    """Materialize a fresh wire model from a carried problem (never mutates it).

    Parameters
    ----------
    problem : Problem
        The raised problem instance (read-only input).
    instance : str | None
        Resolved ``instance`` to use when the problem didn't set one.
    type_uri : str
        The dereferenceable ``type`` URI, resolved from the mounted docs route.

    Returns
    -------
    ProblemDetail
        A brand-new wire model for this request.
    """
    cls = type(problem)
    extensions = {name: getattr(problem, name) for name in extension_fields(cls)}
    return ProblemDetail(
        type=type_uri,
        title=cls.title,
        status=cls.status,
        detail=problem.detail,
        instance=problem.instance if problem.instance is not None else instance,
        **extensions,
    )


def _respond(detail: ProblemDetail) -> Response:
    return Response(
        content=detail.model_dump_json(exclude_none=True),
        status_code=detail.status,
        media_type=PROBLEM_MEDIA_TYPE,
    )


def make_handlers(*, strip_debug: bool, instance_from_request: bool) -> dict[type, Handler]:
    """Build the exception-type -> handler mapping for ``add_exception_handler``.

    Parameters
    ----------
    strip_debug : bool
        Redact ``detail`` on 500s and the offending ``input`` on 422s.
    instance_from_request : bool
        Auto-fill ``instance`` from the request path when unset.

    Returns
    -------
    dict[type, Handler]
        Mapping suitable for iterating into ``app.add_exception_handler``.
    """

    def _instance(request: Request) -> str | None:
        return request.url.path if instance_from_request else None

    async def problem_handler(request: Request, exc: Problem) -> Response:
        type_uri = resolve_type_uri(request.app, type(exc))
        return _respond(build_wire(exc, instance=_instance(request), type_uri=type_uri))

    async def validation_handler(request: Request, exc: RequestValidationError) -> Response:
        params: list[InvalidParam] = []
        for err in exc.errors():
            loc = list(err["loc"])
            param = InvalidParam(
                loc=loc,
                detail=err["msg"],
                type=err["type"],
                input=None if strip_debug or "input" not in err else jsonable_encoder(err["input"]),
            )
            params.append(param)
        n = len(params)
        wire = ProblemDetail.model_validate(
            {
                "type": resolve_type_uri(request.app, ValidationProblem),
                "title": ValidationProblem.title,
                "status": ValidationProblem.status,
                "detail": f"Request validation failed ({n} error{'' if n == 1 else 's'}).",
                "instance": _instance(request),
                "errors": [p.model_dump(exclude_none=True) for p in params],
            }
        )
        return _respond(wire)

    async def http_handler(request: Request, exc: StarletteHTTPException) -> Response:
        try:
            title = HTTPStatus(exc.status_code).phrase
        except ValueError:
            title = "Error"
        wire = ProblemDetail(
            type="about:blank",
            title=title,
            status=exc.status_code,
            detail=exc.detail if isinstance(exc.detail, str) else None,
            instance=_instance(request),
        )
        response = _respond(wire)
        if exc.headers:
            response.headers.update(exc.headers)
        return response

    async def unhandled_handler(request: Request, exc: Exception) -> Response:
        wire = ProblemDetail(
            type=resolve_type_uri(request.app, InternalServerError),
            title=InternalServerError.title,
            status=InternalServerError.status,
            detail=None if strip_debug else f"{type(exc).__name__}: {exc}",
            instance=_instance(request),
        )
        return _respond(wire)

    return cast(
        dict[type, Handler],
        {
            Problem: problem_handler,
            RequestValidationError: validation_handler,
            StarletteHTTPException: http_handler,
            Exception: unhandled_handler,
        },
    )
