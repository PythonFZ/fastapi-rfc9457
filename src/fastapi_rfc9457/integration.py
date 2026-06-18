"""Explicit, named wiring: handlers + OpenAPI registration."""

from __future__ import annotations

import warnings
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from .handlers import make_handlers
from .openapi import register_problem_components
from .problem import _REGISTRY

_INSTALLED_FLAG = "_fastapi_rfc9457_installed"


def add_problem_handlers(
    app: FastAPI,
    *,
    strip_debug: bool = False,
    instance_from_request: bool = True,
) -> None:
    """Register the four problem handlers and the OpenAPI component registration.

    Does **not** mount the docs router (mount it explicitly). Idempotent: a second
    call warns and returns.

    Parameters
    ----------
    app : FastAPI
        The application to wire.
    strip_debug : bool, optional
        Redact ``detail`` on 500s and the offending ``input`` on 422s, by default
        False.
    instance_from_request : bool, optional
        Auto-fill ``instance`` from the request path when unset, by default True.
    """
    if getattr(app.state, _INSTALLED_FLAG, False):
        warnings.warn(
            "add_problem_handlers was called more than once on this app; ignoring the repeat.",
            stacklevel=2,
        )
        return

    handlers = make_handlers(strip_debug=strip_debug, instance_from_request=instance_from_request)
    for exc_type, handler in handlers.items():
        app.add_exception_handler(exc_type, handler)

    register_problem_components(app)
    setattr(app.state, _INSTALLED_FLAG, True)


@asynccontextmanager
async def problem_details_lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Composable lifespan: validate the problem-type registry on startup.

    Nest this inside your own lifespan (user lifespan outer, ours inner). It
    fails fast if any registered problem type is missing ``title`` or ``status``;
    duplicate type URIs are already rejected at class-definition time.

    Parameters
    ----------
    app : FastAPI
        The application (unused today; reserved for app-metadata binding).

    Yields
    ------
    None
    """
    for uri, cls in _REGISTRY.items():
        if not getattr(cls, "title", None):
            raise RuntimeError(f"Problem type {cls.__name__} ({uri!r}) is missing a title")
        if not getattr(cls, "status", None):
            raise RuntimeError(f"Problem type {cls.__name__} ({uri!r}) is missing a status")
    yield
