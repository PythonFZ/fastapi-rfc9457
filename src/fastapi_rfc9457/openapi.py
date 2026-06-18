"""OpenAPI integration: the ``problems()`` responses helper and component wiring."""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI
from fastapi.openapi.utils import get_openapi
from pydantic import create_model

from .models import PROBLEM_MEDIA_TYPE, ProblemDetail
from .problem import _REGISTRY, Problem, extension_fields

_REF_TEMPLATE = "#/components/schemas/{model}"


def _wire_schema(cls: type[Problem]) -> dict[str, Any]:
    """Build the per-type wire JSON schema (ProblemDetail + typed extensions)."""
    fields = {name: (typ, ...) for name, typ in extension_fields(cls).items()}
    model = create_model(cls.__name__, __base__=ProblemDetail, **fields)  # type: ignore[call-overload]
    return model.model_json_schema(ref_template=_REF_TEMPLATE)


def problems(*types: type[Problem]) -> dict[int | str, dict[str, Any]]:
    """Build a ``responses=`` mapping under ``application/problem+json``.

    Types sharing a status are merged into one ``oneOf`` entry. The result is a
    plain dict, so it spreads into any ``responses=``.

    Parameters
    ----------
    *types : type[Problem]
        The problem types a route can raise.

    Returns
    -------
    dict[int | str, dict[str, Any]]
        A ``responses=`` mapping keyed by status code.
    """
    grouped: dict[int, list[type[Problem]]] = {}
    for problem_type in types:
        grouped.setdefault(problem_type.status, []).append(problem_type)

    responses: dict[int | str, dict[str, Any]] = {}
    for status, group in grouped.items():
        refs = [{"$ref": _REF_TEMPLATE.format(model=t.__name__)} for t in group]
        schema = refs[0] if len(refs) == 1 else {"oneOf": refs}
        descriptions = [(t.__doc__ or t.title).strip() for t in group]
        responses[status] = {
            "description": " / ".join(descriptions),
            "content": {PROBLEM_MEDIA_TYPE: {"schema": schema}},
        }
    return responses


def register_problem_components(app: FastAPI) -> None:
    """Wrap ``app.openapi`` to inject every registered problem schema.

    The FastAPI-endorsed *Extending OpenAPI* pattern: idempotent, lazily bound to
    app metadata. Lifts nested ``$defs`` into ``components.schemas`` so no ``$ref``
    dangles.

    Parameters
    ----------
    app : FastAPI
        The application whose ``openapi`` callable is wrapped.

    Notes
    -----
    The OpenAPI schema reflects the problem-type registry at the moment it is
    first built (the wrap is lazy and cached). Define/import all ``Problem``
    subclasses before the schema is first generated so every type is documented.
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
        components = schema.setdefault("components", {}).setdefault("schemas", {})

        def _add(name: str, model_schema: dict[str, Any]) -> None:
            defs = model_schema.pop("$defs", {})
            components.setdefault(name, model_schema)
            for def_name, def_schema in defs.items():
                components.setdefault(def_name, def_schema)

        _add("ProblemDetail", ProblemDetail.model_json_schema(ref_template=_REF_TEMPLATE))
        for cls in _REGISTRY.values():
            _add(cls.__name__, _wire_schema(cls))

        app.openapi_schema = schema
        return schema

    app.openapi = custom_openapi  # type: ignore[method-assign]
