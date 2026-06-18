"""Dereferenceable type-doc router, mounted explicitly by the user."""

from __future__ import annotations

import html
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse
from starlette.responses import Response

from .builtins import InternalServerError, ValidationProblem
from .openapi import route_problem_types
from .problem import Problem, extension_fields
from .uris import DOC_ROUTE, doc_route_name, resolve_type_uri, slug_of

_HTML = """<!doctype html><meta charset="utf-8">
<title>{title}</title>
<main style="font-family:system-ui;max-width:48rem;margin:3rem auto;line-height:1.6">
<h1>{title} <small style="color:#888">{status}</small></h1>
<p><code>{type}</code></p>
<p>{description}</p>
<h2>Extension members</h2>
<ul>{members}</ul>
</main>"""


def _format_type(typ: Any) -> str:
    """Render a type annotation as a short, readable name.

    Plain classes use their bare ``__name__`` (``int`` rather than the repr
    ``<class 'int'>``); parameterized generics fall back to ``str`` (``list[str]``).

    Parameters
    ----------
    typ : Any
        A resolved type annotation.

    Returns
    -------
    str
        A human-readable rendering of the annotation.
    """
    return typ.__name__ if isinstance(typ, type) else str(typ)


def _payload(cls: type[Problem], type_uri: str) -> dict[str, Any]:
    return {
        "type": type_uri,
        "title": cls.title,
        "status": cls.status,
        "description": (cls.__doc__ or "").strip(),
        "extensions": {name: _format_type(typ) for name, typ in extension_fields(cls).items()},
    }


def _render(cls: type[Problem], request: Request) -> Response:
    data = _payload(cls, resolve_type_uri(request.app, cls))
    if "text/html" in request.headers.get("accept", ""):
        members = "".join(
            f"<li><code>{html.escape(name)}</code>: {html.escape(typ)}</li>"
            for name, typ in data["extensions"].items()
        )
        escaped = {k: html.escape(str(v)) for k, v in data.items() if k != "extensions"}
        return HTMLResponse(_HTML.format(members=members, **escaped))
    return JSONResponse(data)


def _documented_types(app: Any) -> list[type[Problem]]:
    """Types whose doc pages this app serves: those on its routes plus the two
    builtins ``add_problem_handlers`` always emits (validation 422, unhandled 500)."""
    seen = {cls.type: cls for cls in route_problem_types(app)}
    for cls in (ValidationProblem, InternalServerError):
        seen.setdefault(cls.type, cls)
    return list(seen.values())


def get_problem_docs_router(*types: type[Problem]) -> APIRouter:
    """Return a router serving one doc page per problem type.

    Two modes:

    * **Route-derived (no arguments).** Serves a page for every problem type the
      app declares via ``responses=problems(...)`` (plus the always-on validation
      and internal-error types), resolved from the request's app at call time.
      Adding a new type to a route is the only change needed — nothing to restate
      here.
    * **Explicit.** Pass specific types to publish exactly those pages (useful for
      a standalone docs app with no routes raising them).

    Parameters
    ----------
    *types : type[Problem]
        The types to document, or none to derive them from the app's routes.

    Returns
    -------
    APIRouter
        Mount it yourself with ``app.include_router(..., prefix=..., tags=...)``;
        point your ``type`` URIs at the chosen prefix.
    """
    router = APIRouter()

    if not types:

        async def endpoint(slug: str, request: Request) -> Response:
            available = {slug_of(cls): cls for cls in _documented_types(request.app)}
            match = available.get(slug)
            if match is None:
                raise HTTPException(
                    status_code=404, detail=f"No problem type documented at {slug!r}"
                )
            return _render(match, request)

        router.add_api_route(
            "/{slug}",
            endpoint,
            methods=["GET"],
            name=DOC_ROUTE,
            summary="Problem type documentation",
        )
        return router

    for cls in types:
        slug = slug_of(cls)

        def make_endpoint(problem_cls: type[Problem]):
            async def endpoint(request: Request) -> Response:
                return _render(problem_cls, request)

            return endpoint

        router.add_api_route(
            f"/{slug}",
            make_endpoint(cls),
            methods=["GET"],
            name=doc_route_name(slug),
            summary=f"{cls.title} ({cls.status})",
        )

    return router
