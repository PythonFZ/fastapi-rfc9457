"""The four exception handlers and the per-request wire-model builder."""

from __future__ import annotations

import warnings
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass
from http import HTTPStatus
from typing import cast

from fastapi import FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.responses import Response

from .builtins import InternalServerError, InvalidParam, ValidationProblem
from .models import PROBLEM_MEDIA_TYPE, ProblemDetail
from .problem import (
    Problem,
    UndeclaredHeaderWarning,
    extension_fields,
    require_concrete,
    sent_headers,
)
from .uris import resolve_type_uri

Handler = Callable[[Request, Exception], Awaitable[Response]]

_BUILTINS_STATE = "_fastapi_rfc9457_builtins"


@dataclass(frozen=True)
class BuiltinProblems:
    """The problem classes the validation and unhandled-exception handlers answer with.

    Parameters
    ----------
    validation : type[ValidationProblem]
        The class a request-validation failure answers with.
    internal : type[InternalServerError]
        The class an unhandled exception answers with.

    Raises
    ------
    TypeError
        If a class subclasses a different default, is abstract, changes the
        default's ``status`` or declares extension fields of its own.
    """

    validation: type[ValidationProblem] = ValidationProblem
    internal: type[InternalServerError] = InternalServerError

    def __post_init__(self) -> None:
        for name, cls, default in (
            ("validation", self.validation, ValidationProblem),
            ("internal", self.internal, InternalServerError),
        ):
            if not (isinstance(cls, type) and issubclass(cls, default)):
                raise TypeError(f"{name}= takes a subclass of {default.__name__}; got {cls!r}.")
            require_concrete(cls)
            if cls.status != default.status:
                raise TypeError(
                    f"{name}={cls.__name__} answers with status {default.status}; "
                    f"it sets {cls.status}."
                )
            added = extension_fields(cls).keys() - extension_fields(default).keys()
            if added:
                raise TypeError(
                    f"{name}={cls.__name__} carries the extension fields of "
                    f"{default.__name__}; it adds {sorted(added)}."
                )

    def store(self, app: FastAPI) -> None:
        """Record these classes on ``app.state`` for the OpenAPI and docs builders."""
        setattr(app.state, _BUILTINS_STATE, self)

    @classmethod
    def of(cls, app: FastAPI) -> BuiltinProblems:
        """Return the classes stored on ``app``; the defaults for an unwired app."""
        return getattr(app.state, _BUILTINS_STATE, cls())


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


def _respond(detail: ProblemDetail, headers: Mapping[str, str] | None = None) -> Response:
    return Response(
        content=detail.model_dump_json(exclude_none=True),
        status_code=detail.status,
        headers=headers,
        media_type=PROBLEM_MEDIA_TYPE,
    )


def _warn_undeclared_headers(cls: type[Problem], headers: Mapping[str, str]) -> None:
    declared = {name.lower() for name in cls.headers}
    for name in headers:
        if name.lower() not in declared:
            warnings.warn(
                f"{cls.__name__} sends {name!r}, which is missing from "
                f"{cls.__name__}.headers; declare it there to document it in OpenAPI.",
                UndeclaredHeaderWarning,
                stacklevel=2,
            )


def make_handlers(
    *,
    strip_debug: bool,
    instance_from_request: bool,
    builtins: BuiltinProblems = BuiltinProblems(),
) -> dict[type, Handler]:
    """Build the exception-type -> handler mapping for ``add_exception_handler``.

    Parameters
    ----------
    strip_debug : bool
        Redact ``detail`` on 500s and the offending ``input`` on 422s.
    instance_from_request : bool
        Auto-fill ``instance`` from the request path when unset.
    builtins : BuiltinProblems, optional
        The classes the 422 and 500 handlers answer with.

    Returns
    -------
    dict[type, Handler]
        Mapping suitable for iterating into ``app.add_exception_handler``.
    """
    validation, internal = builtins.validation, builtins.internal

    def _instance(request: Request) -> str | None:
        return request.url.path if instance_from_request else None

    async def problem_handler(request: Request, exc: Problem) -> Response:
        type_uri = resolve_type_uri(request.app, type(exc))
        wire = build_wire(exc, instance=_instance(request), type_uri=type_uri)
        headers = sent_headers(exc)
        _warn_undeclared_headers(type(exc), headers)
        return _respond(wire, headers)

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
                "type": resolve_type_uri(request.app, validation),
                "title": validation.title,
                "status": validation.status,
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
        return _respond(wire, exc.headers)

    async def unhandled_handler(request: Request, exc: Exception) -> Response:
        wire = ProblemDetail(
            type=resolve_type_uri(request.app, internal),
            title=internal.title,
            status=internal.status,
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
