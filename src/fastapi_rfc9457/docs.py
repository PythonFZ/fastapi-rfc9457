"""Dereferenceable type-doc router, mounted explicitly by the user."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, JSONResponse
from starlette.responses import Response

from .problem import _REGISTRY, Problem, extension_fields

_HTML = """<!doctype html><meta charset="utf-8">
<title>{title}</title>
<main style="font-family:system-ui;max-width:48rem;margin:3rem auto;line-height:1.6">
<h1>{title} <small style="color:#888">{status}</small></h1>
<p><code>{type}</code></p>
<p>{description}</p>
<h2>Extension members</h2>
<ul>{members}</ul>
</main>"""


def _payload(cls: type[Problem]) -> dict[str, Any]:
    return {
        "type": cls.type,
        "title": cls.title,
        "status": cls.status,
        "description": (cls.__doc__ or "").strip(),
        "extensions": {name: str(typ) for name, typ in extension_fields(cls).items()},
    }


def _slug(cls: type[Problem]) -> str:
    return (cls.type or "").rsplit("/", 1)[-1]


def get_problem_docs_router(*types: type[Problem]) -> APIRouter:
    """Return a router serving one doc page per problem type.

    Parameters
    ----------
    *types : type[Problem]
        The types to document. If empty, every registered type is served.

    Returns
    -------
    APIRouter
        Mount it yourself with ``app.include_router(..., prefix=..., tags=...)``;
        point your ``type`` URIs at the chosen prefix.
    """
    router = APIRouter()
    selected = list(types) if types else list(_REGISTRY.values())

    for cls in selected:
        slug = _slug(cls)

        def make_endpoint(problem_cls: type[Problem]):
            async def endpoint(request: Request) -> Response:
                data = _payload(problem_cls)
                if "text/html" in request.headers.get("accept", ""):
                    members = "".join(
                        f"<li><code>{name}</code>: {typ}</li>"
                        for name, typ in data["extensions"].items()
                    )
                    return HTMLResponse(_HTML.format(members=members, **data))
                return JSONResponse(data)

            return endpoint

        router.add_api_route(
            f"/{slug}",
            make_endpoint(cls),
            methods=["GET"],
            name=f"problem-doc-{slug}",
            summary=f"{cls.title} ({cls.status})",
        )

    return router
