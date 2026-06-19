"""OpenAPI integration: the ``problems()`` responses helper and component wiring.

The design mirrors ``fastapi-pagination``'s ``add_pagination(app)``: routes carry
real model objects (via FastAPI's native ``responses={status: {"model": ...}}``),
and a single ``app.openapi`` wrap recovers them by walking the routes. FastAPI
auto-registers the component schemas for us; the wrap only normalizes each
response to ``application/problem+json`` (FastAPI emits models under
``application/json``), converts unions to ``oneOf``, rewrites the auto-generated
422, and validates type-URI uniqueness at build time. No global registry.
"""

from __future__ import annotations

import json
import types
from functools import reduce
from operator import or_
from typing import Any, Literal, Union, get_args, get_origin

from fastapi import FastAPI
from fastapi.openapi.utils import get_openapi
from fastapi.routing import APIRoute, iter_route_contexts
from pydantic import BaseModel, ConfigDict, create_model

from .builtins import ValidationProblem
from .models import PROBLEM_MEDIA_TYPE, ProblemDetail
from .problem import Problem, extension_fields
from .uris import resolve_type_uri

_REF_TEMPLATE = "#/components/schemas/{model}"
_HTTP_VALIDATION_ERROR = _REF_TEMPLATE.format(model="HTTPValidationError")

# Memoized per-type wire models, keyed by source class identity. This is a cache
# for correct/stable component naming (one component per type, not per route) —
# not a discovery registry: what gets documented is decided by the routes.
_WIRE_CACHE: dict[type[Problem], type[BaseModel]] = {}


class _WireBase(ProblemDetail):
    """Closed (``extra='forbid'``) variant of :class:`ProblemDetail` for docs.

    The open base carries unknown members for client parsing; a *documented*
    problem type has a known, closed set of extensions, so its schema forbids
    extras (no ``additionalProperties: true`` noise in the rendered docs).
    """

    model_config = ConfigDict(extra="forbid")


def _literal(value: object) -> Any:
    """Build a single-value ``Literal`` from a runtime value (inherently dynamic)."""
    return Literal[value]  # type: ignore[valid-type]


def _union(models: list[type[BaseModel]]) -> Any:
    """Combine 2+ models into a single ``X | Y`` union type (for a shared status)."""
    return reduce(or_, models)


def _wire_model(cls: type[Problem]) -> type[BaseModel]:
    """Build (or reuse) the per-type wire model: closed, const ``type``/``status``.

    Parameters
    ----------
    cls : type[Problem]
        The authored problem type.

    Returns
    -------
    type[BaseModel]
        A Pydantic model named ``cls.__name__`` whose ``type`` and ``status`` are
        pinned to the class's values, carrying ``__problem_source__`` for recovery.
    """
    cached = _WIRE_CACHE.get(cls)
    if cached is not None:
        return cached
    fields: dict[str, Any] = {name: (typ, ...) for name, typ in extension_fields(cls).items()}
    model = create_model(  # type: ignore[call-overload]
        cls.__name__,
        __base__=_WireBase,
        type=(_literal(cls.type), cls.type),
        status=(_literal(cls.status), cls.status),
        title=(str, cls.title),
        **fields,
    )
    model.__problem_source__ = cls  # type: ignore[attr-defined]
    _WIRE_CACHE[cls] = model
    return model


def problems(*types_: type[Problem]) -> dict[int | str, dict[str, Any]]:
    """Build a ``responses=`` mapping for the given problem types.

    Types sharing a status are merged into one response. The result spreads into
    any ``responses=``. The actual ``application/problem+json`` media type and
    ``oneOf`` shaping are applied at OpenAPI build time by
    :func:`register_problem_components` (wired through :func:`add_problem_handlers`).

    Parameters
    ----------
    *types_ : type[Problem]
        The problem types a route can raise.

    Returns
    -------
    dict[int | str, dict[str, Any]]
        A ``responses=`` mapping keyed by status code.
    """
    grouped: dict[int, list[type[Problem]]] = {}
    for problem_type in types_:
        grouped.setdefault(problem_type.status, []).append(problem_type)

    responses: dict[int | str, dict[str, Any]] = {}
    for status, group in grouped.items():
        wires = [_wire_model(t) for t in group]
        model: Any = wires[0] if len(wires) == 1 else _union(wires)
        descriptions = [(t.__doc__ or t.title).strip() for t in group]
        responses[status] = {"model": model, "description": " / ".join(descriptions)}
    return responses


def _problem_wire_members(model: Any) -> list[type[BaseModel]] | None:
    """Return the problem wire models behind a response ``model``, or ``None``.

    Handles both a single wire model and a ``Union`` of them. Returns ``None`` for
    anything that isn't (entirely) our wire models, so user responses are untouched.
    """
    if model is None:
        return None
    is_union = get_origin(model) in (Union, types.UnionType)
    members = list(get_args(model)) if is_union else [model]
    if members and all(getattr(m, "__problem_source__", None) is not None for m in members):
        return members
    return None


def route_problem_types(app: FastAPI) -> list[type[Problem]]:
    """Return the problem types an app declares on its routes, in first-seen order.

    Recovers the authored :class:`Problem` classes from each route's
    ``responses=problems(...)`` (the same recovery the OpenAPI wrap performs), so
    callers never restate the type list. Deduplicated by class identity.

    Parameters
    ----------
    app : FastAPI
        The application to inspect.

    Returns
    -------
    list[type[Problem]]
        Every problem type referenced by the app's route responses.
    """
    seen: dict[type[Problem], None] = {}

    for ctx in iter_route_contexts(app.routes):
        route = ctx.original_route
        if not isinstance(route, APIRoute):
            continue
        for entry in route.responses.values():
            members = _problem_wire_members(entry.get("model"))
            if members is None:
                continue
            for member in members:
                seen.setdefault(member.__problem_source__, None)  # type: ignore[attr-defined]
    return list(seen)


def _ref_schema(
    members: list[type[BaseModel]], seen_uris: dict[str, type[Problem]], app: FastAPI
) -> dict[str, Any]:
    """Build the ``$ref``/``oneOf`` schema for a response, checking URI uniqueness."""
    refs: list[dict[str, Any]] = []
    for member in members:
        source: type[Problem] = member.__problem_source__  # type: ignore[attr-defined]
        uri = resolve_type_uri(app, source)
        existing = seen_uris.get(uri)
        if existing is not None and existing is not source:
            raise ValueError(
                f"Duplicate problem type URI {uri!r}: {existing.__name__} and "
                f"{source.__name__}. Give each Problem subclass a distinct `type`."
            )
        seen_uris[uri] = source
        refs.append({"$ref": _REF_TEMPLATE.format(model=member.__name__)})
    return refs[0] if len(refs) == 1 else {"oneOf": refs}


_JSON_SAMPLES: dict[str | None, Any] = {
    "string": "string",
    "integer": 0,
    "number": 0.0,
    "boolean": True,
}


def _sample_value(prop: dict[str, Any], defs: dict[str, Any]) -> Any:
    """Produce a representative sample value for one JSON-Schema property.

    Pinned values win (``const`` then ``default``); otherwise a placeholder is
    chosen by JSON type. ``$ref`` is resolved through ``defs`` and ``anyOf``/
    ``oneOf`` follow the first non-null branch, mirroring the concrete shape a
    client would send.

    Parameters
    ----------
    prop : dict[str, Any]
        A JSON-Schema property subschema.
    defs : dict[str, Any]
        The owning schema's ``$defs`` map, for resolving ``$ref``.

    Returns
    -------
    Any
        A JSON-serializable sample value.
    """
    if "const" in prop:
        return prop["const"]
    if "default" in prop:
        return prop["default"]
    if "$ref" in prop:
        return _sample_value(defs.get(prop["$ref"].rsplit("/", 1)[-1], {}), defs)
    for branch_key in ("anyOf", "oneOf"):
        branches = [b for b in prop.get(branch_key, ()) if b.get("type") != "null"]
        if branches:
            return _sample_value(branches[0], defs)
    json_type = prop.get("type")
    if json_type == "array":
        items = prop.get("items")
        return [_sample_value(items, defs)] if items else []
    if json_type == "object":
        return {n: _sample_value(s, defs) for n, s in prop.get("properties", {}).items()}
    return _JSON_SAMPLES.get(json_type)


def _example_for(model: type[BaseModel]) -> dict[str, Any]:
    """Build one representative example payload for a problem wire model.

    Includes the identity members the type fixes (the ``type``/``status`` consts
    and the ``title`` default) plus every required extension member, each filled
    with a JSON-type-appropriate sample. Optional members (``detail``,
    ``instance``) are omitted — they carry no canonical per-type example value.

    Parameters
    ----------
    model : type[BaseModel]
        A problem wire model (from :func:`_wire_model`).

    Returns
    -------
    dict[str, Any]
        A JSON object suitable as an OpenAPI example ``value``.
    """
    schema = model.model_json_schema(ref_template=_REF_TEMPLATE)
    defs = schema.get("$defs", {})
    required = set(schema.get("required", ()))
    example: dict[str, Any] = {}
    for name, prop in schema.get("properties", {}).items():
        if name in required or "const" in prop or prop.get("default") is not None:
            example[name] = _sample_value(prop, defs)
    return example


def _problem_examples(members: list[type[BaseModel]]) -> dict[str, Any]:
    """Build a named OpenAPI ``examples`` map, one entry per ``oneOf`` member.

    Swagger UI synthesizes only a single example from a ``oneOf`` schema (the
    first branch), hiding every sibling. Explicit named examples make it render
    a dropdown with one labelled payload per problem type.

    Parameters
    ----------
    members : list[type[BaseModel]]
        The problem wire models behind a shared-status response.

    Returns
    -------
    dict[str, Any]
        An OpenAPI ``examples`` map keyed by wire-model name.
    """
    examples: dict[str, Any] = {}
    for member in members:
        source: type[Problem] = member.__problem_source__  # type: ignore[attr-defined]
        examples[member.__name__] = {
            "summary": f"{source.title} ({source.status})",
            "value": _example_for(member),
        }
    return examples


def _ensure_component(components: dict[str, Any], model: type[BaseModel]) -> None:
    """Add ``model``'s JSON schema (lifting nested ``$defs``) if not already present."""
    schema = model.model_json_schema(ref_template=_REF_TEMPLATE)
    defs = schema.pop("$defs", {})
    components.setdefault(model.__name__, schema)
    for name, sub_schema in defs.items():
        components.setdefault(name, sub_schema)


def _rewrite_validation_responses(paths: dict[str, Any], components: dict[str, Any]) -> None:
    """Rewrite FastAPI's auto-generated 422 to ``application/problem+json``.

    The runtime already emits ``ValidationProblem`` as ``application/problem+json``;
    this aligns the *documentation* (RFC 9457 §3) for every route FastAPI gave a
    default ``HTTPValidationError`` 422.
    """
    rewrote = False
    for path_item in paths.values():
        if not isinstance(path_item, dict):
            continue
        for operation in path_item.values():
            if not isinstance(operation, dict) or "responses" not in operation:
                continue
            response = operation["responses"].get("422")
            if not isinstance(response, dict):
                continue
            schema = response.get("content", {}).get("application/json", {}).get("schema", {})
            if schema.get("$ref") == _HTTP_VALIDATION_ERROR:
                response["content"] = {
                    PROBLEM_MEDIA_TYPE: {
                        "schema": {"$ref": _REF_TEMPLATE.format(model="ValidationProblem")}
                    }
                }
                rewrote = True
    if rewrote:
        _ensure_component(components, _wire_model(ValidationProblem))


def _retarget_type_uris(schema: dict[str, Any], app: FastAPI) -> None:
    """Point each problem ``type`` const at its live doc-page URL.

    FastAPI bakes ``type`` into every problem component as a ``const`` taken from
    the class's declared id. This rewrites those consts (and any inline ``oneOf``
    example values) to the URI resolved against the mounted docs route, so the
    documented ``type`` matches what the runtime handlers emit (issue #6).
    """
    components: dict[str, Any] = schema.get("components", {}).get("schemas", {})
    sources = list(route_problem_types(app))
    if "ValidationProblem" in components:
        sources.append(ValidationProblem)
    uri_by_name = {cls.__name__: resolve_type_uri(app, cls) for cls in sources}

    for name, uri in uri_by_name.items():
        type_schema = components.get(name, {}).get("properties", {}).get("type")
        if isinstance(type_schema, dict):
            type_schema["const"] = uri
            type_schema["default"] = uri

    for path_item in schema.get("paths", {}).values():
        if not isinstance(path_item, dict):
            continue
        for operation in path_item.values():
            if not isinstance(operation, dict):
                continue
            for response in operation.get("responses", {}).values():
                if not isinstance(response, dict):
                    continue
                for media in response.get("content", {}).values():
                    for ex_name, example in media.get("examples", {}).items():
                        value = example.get("value")
                        if ex_name in uri_by_name and isinstance(value, dict):
                            value["type"] = uri_by_name[ex_name]


def _prune_unreferenced(schema: dict[str, Any], names: tuple[str, ...]) -> None:
    """Drop named components no longer pointed at by any ``$ref`` (cleanup pass)."""
    schemas = schema.get("components", {}).get("schemas", {})
    for name in names:
        # Re-serialize each pass: removing one component frees refs held only by it.
        if f'"{_REF_TEMPLATE.format(model=name)}"' not in json.dumps(schema):
            schemas.pop(name, None)


def register_problem_components(app: FastAPI) -> None:
    """Wrap ``app.openapi`` to normalize problem responses and components.

    The FastAPI-endorsed *Extending OpenAPI* pattern: idempotent and lazy, so it
    sees every route regardless of when it is called. It recovers the problem
    types each route declares (from the response models), rewrites them to
    ``application/problem+json`` (``oneOf`` for a shared status), aligns the
    auto-generated 422, and raises if two types share a ``type`` URI.

    Parameters
    ----------
    app : FastAPI
        The application whose ``openapi`` callable is wrapped.
    """

    def custom_openapi() -> dict[str, Any]:
        if app.openapi_schema:
            return app.openapi_schema
        schema = get_openapi(
            title=app.title,
            version=app.version,
            openapi_version=app.openapi_version,
            summary=app.summary,
            description=app.description,
            routes=app.routes,
            webhooks=app.webhooks.routes,
            tags=app.openapi_tags,
            servers=app.servers,
            terms_of_service=app.terms_of_service,
            contact=app.contact,
            license_info=app.license_info,
        )
        paths: dict[str, Any] = schema.get("paths", {})
        components: dict[str, Any] = schema.setdefault("components", {}).setdefault("schemas", {})

        seen_uris: dict[str, type[Problem]] = {}

        for ctx in iter_route_contexts(app.routes):
            route = ctx.original_route
            methods = ctx.methods
            path = ctx.path_format
            if not isinstance(route, APIRoute) or not methods or path is None:
                continue
            path_item = paths.get(path)
            if path_item is None:
                continue
            for status, entry in route.responses.items():
                members = _problem_wire_members(entry.get("model"))
                if members is None:
                    continue
                content_schema = _ref_schema(members, seen_uris, app)
                media: dict[str, Any] = {"schema": content_schema}
                if len(members) > 1:
                    # Swagger UI samples only the first oneOf branch; name an
                    # example per member so it offers a per-type dropdown.
                    media["examples"] = _problem_examples(members)
                for method in methods:
                    operation = path_item.get(method.lower())
                    if not isinstance(operation, dict):
                        continue
                    response = operation.get("responses", {}).get(str(status))
                    if response is not None:
                        response["content"] = {PROBLEM_MEDIA_TYPE: media}

        _rewrite_validation_responses(paths, components)
        _ensure_component(components, ProblemDetail)  # canonical open base shape
        _retarget_type_uris(schema, app)  # consts track the mounted docs prefix
        _prune_unreferenced(schema, ("HTTPValidationError", "ValidationError"))

        app.openapi_schema = schema
        return schema

    app.openapi = custom_openapi  # type: ignore[method-assign]
