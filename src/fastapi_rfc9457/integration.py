"""Explicit, named wiring: handlers + OpenAPI registration."""

from __future__ import annotations

import warnings
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from typing_extensions import deprecated

from .builtins import _BUILTINS_STATE, BuiltinProblems, InternalServerError, ValidationProblem
from .handlers import make_handlers
from .openapi import register_problem_components


def add_problem_handlers(
    app: FastAPI,
    *,
    strip_debug: bool = False,
    instance_from_request: bool = True,
    validation: type[ValidationProblem] = ValidationProblem,
    internal: type[InternalServerError] = InternalServerError,
) -> None:
    """Register the four problem handlers and the OpenAPI component registration.

    Mount the docs router separately. A second call with the same ``validation``
    and ``internal`` warns and returns.

    Parameters
    ----------
    app : FastAPI
        The application to wire.
    strip_debug : bool, optional
        Redact ``detail`` on 500s and the offending ``input`` on 422s, by default
        False.
    instance_from_request : bool, optional
        Auto-fill ``instance`` from the request path when unset, by default True.
    validation : type[ValidationProblem], optional
        Class for 422 responses, the OpenAPI 422 schema and its docs page.
    internal : type[InternalServerError], optional
        Class for 500 responses and its docs page.

    Raises
    ------
    TypeError
        If ``validation`` or ``internal`` is outside its default's hierarchy,
        abstract, sets another ``status``, or adds an extension field without a
        default.
    ValueError
        If an earlier call wired the app with other ``validation`` or ``internal``
        classes.
    """
    builtins = BuiltinProblems(validation=validation, internal=internal)
    wired: BuiltinProblems | None = getattr(app.state, _BUILTINS_STATE, None)
    if wired is not None:
        if wired != builtins:
            raise ValueError(
                f"add_problem_handlers wired this app with validation={wired.validation.__name__}, "
                f"internal={wired.internal.__name__}; this call passes "
                f"validation={validation.__name__}, internal={internal.__name__}."
            )
        warnings.warn(
            "add_problem_handlers was called more than once on this app; ignoring the repeat.",
            stacklevel=2,
        )
        return

    handlers = make_handlers(
        strip_debug=strip_debug, instance_from_request=instance_from_request, builtins=builtins
    )
    for exc_type, handler in handlers.items():
        app.add_exception_handler(exc_type, handler)

    setattr(app.state, _BUILTINS_STATE, builtins)
    register_problem_components(app)


@deprecated("Problem types are validated when defined; drop problem_details_lifespan.")
@asynccontextmanager
async def problem_details_lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Deprecated no-op lifespan; problem types are validated when defined.

    Parameters
    ----------
    app : FastAPI
        The application.

    Yields
    ------
    None
    """
    yield
