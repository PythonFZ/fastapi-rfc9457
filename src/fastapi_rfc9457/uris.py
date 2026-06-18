"""Resolve a problem ``type`` URI from the mounted docs route.

A problem type's *identity* is its slug (the last path segment); its *location*
is wherever the docs router is mounted. Rather than hard-coding the location on
each class, the emitted ``type`` is reverse-routed against the app at serialize
and OpenAPI-build time, so the URI always points at the live doc page and tracks
the mount prefix automatically (issue #6).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from starlette.routing import NoMatchFound

if TYPE_CHECKING:
    from fastapi import FastAPI

    from .problem import Problem

#: Route name used by the route-derived (single ``/{slug}``) docs endpoint.
DOC_ROUTE = "problem-doc"


def doc_route_name(slug: str) -> str:
    """Return the route name of an explicitly-published doc page.

    Parameters
    ----------
    slug : str
        The problem type's slug.

    Returns
    -------
    str
        The ``name=`` used when registering that type's explicit doc route.
    """
    return f"problem-doc-{slug}"


def slug_from_uri(uri: str) -> str:
    """Return the slug (last path segment) of a ``type`` URI reference.

    Parameters
    ----------
    uri : str
        A ``type`` URI reference, relative or absolute.

    Returns
    -------
    str
        The last path segment, e.g. ``"out-of-credit"`` for both
        ``"out-of-credit"`` and ``"/problems/out-of-credit"``.
    """
    return uri.rsplit("/", 1)[-1]


def slug_of(cls: type[Problem]) -> str:
    """Return a problem type's slug: the last path segment of its ``type`` id.

    Parameters
    ----------
    cls : type[Problem]
        A ``Problem`` subclass.

    Returns
    -------
    str
        The slug, e.g. ``"out-of-credit"`` for ``"/problems/out-of-credit"`` or a
        bare derived ``"out-of-credit"``.
    """
    return slug_from_uri(cls.type or "")


def resolve_type_uri(app: FastAPI, cls: type[Problem]) -> str:
    """Return the dereferenceable ``type`` URI for a problem class.

    Reverse-routes the type's slug against the app's mounted docs router so the
    URI points at the actual doc page regardless of the mount prefix. Tries the
    route-derived endpoint first, then an explicitly-published one.

    Parameters
    ----------
    app : FastAPI
        The application handling the request / building the schema.
    cls : type[Problem]
        The problem type to resolve.

    Returns
    -------
    str
        The doc-page path (e.g. ``"/v1/problems/out-of-credit"``) when the docs
        router is mounted; otherwise the class's declared ``type`` verbatim — a
        valid RFC 9457 relative reference that simply isn't dereferenceable.
    """
    slug = slug_of(cls)
    try:
        return str(app.url_path_for(DOC_ROUTE, slug=slug))
    except NoMatchFound:
        pass
    try:
        return str(app.url_path_for(doc_route_name(slug)))
    except NoMatchFound:
        pass
    return cls.type or "about:blank"
