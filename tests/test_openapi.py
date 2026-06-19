import json
import re
from typing import Annotated

import pytest
from fastapi import APIRouter, FastAPI, Query
from fastapi.testclient import TestClient

from fastapi_rfc9457.models import PROBLEM_MEDIA_TYPE
from fastapi_rfc9457.openapi import problems, register_problem_components, route_problem_types
from fastapi_rfc9457.problem import Problem


class AlphaGone(Problem):
    """Alpha is gone."""

    type = "/problems/alpha-gone"
    title = "Gone"
    status = 410


class BetaGone(Problem):
    """Beta is gone."""

    type = "/problems/beta-gone"
    title = "Gone"
    status = 410


class Charged(Problem):
    """Charged."""

    type = "/problems/charged"
    title = "Out of Credit"
    status = 403
    balance: int


class Suspended(Problem):
    """Account suspended."""

    type = "/problems/suspended"
    title = "Suspended"
    status = 403


def _openapi(app: FastAPI) -> dict:
    register_problem_components(app)
    return TestClient(app).get("/openapi.json").json()


def test_route_response_uses_problem_media_type_and_ref():
    app = FastAPI()

    @app.get("/c", responses=problems(Charged))
    async def c() -> dict:
        return {}

    doc = _openapi(app)
    resp = doc["paths"]["/c"]["get"]["responses"]["403"]
    assert list(resp["content"]) == [PROBLEM_MEDIA_TYPE]
    assert resp["content"][PROBLEM_MEDIA_TYPE]["schema"] == {"$ref": "#/components/schemas/Charged"}
    assert "Charged" in doc["components"]["schemas"]


def test_shared_status_merges_into_oneof():
    app = FastAPI()

    @app.get("/g", responses=problems(AlphaGone, BetaGone))
    async def g() -> dict:
        return {}

    doc = _openapi(app)
    schema = doc["paths"]["/g"]["get"]["responses"]["410"]["content"][PROBLEM_MEDIA_TYPE]["schema"]
    assert schema == {
        "oneOf": [
            {"$ref": "#/components/schemas/AlphaGone"},
            {"$ref": "#/components/schemas/BetaGone"},
        ]
    }


def test_oneof_response_attaches_named_example_per_member():
    app = FastAPI()

    @app.get("/g", responses=problems(AlphaGone, BetaGone))
    async def g() -> dict:
        return {}

    media = _openapi(app)["paths"]["/g"]["get"]["responses"]["410"]["content"][PROBLEM_MEDIA_TYPE]
    examples = media["examples"]
    assert set(examples) == {"AlphaGone", "BetaGone"}
    assert examples["AlphaGone"]["summary"] == "Gone (410)"
    assert examples["AlphaGone"]["value"]["type"] == "/problems/alpha-gone"
    assert examples["AlphaGone"]["value"]["status"] == 410
    assert examples["BetaGone"]["value"]["type"] == "/problems/beta-gone"


def test_oneof_example_includes_required_extension_members():
    app = FastAPI()

    @app.get("/p", responses=problems(Charged, Suspended))
    async def p() -> dict:
        return {}

    examples = _openapi(app)["paths"]["/p"]["get"]["responses"]["403"]["content"][
        PROBLEM_MEDIA_TYPE
    ]["examples"]
    charged = examples["Charged"]["value"]
    assert charged["type"] == "/problems/charged"
    assert isinstance(charged["balance"], int)  # required extension member sampled
    # a sibling without that extension does not carry it, nor optional members:
    assert "balance" not in examples["Suspended"]["value"]
    assert "detail" not in charged


def test_single_type_response_omits_examples():
    app = FastAPI()

    @app.get("/c", responses=problems(Charged))
    async def c() -> dict:
        return {}

    media = _openapi(app)["paths"]["/c"]["get"]["responses"]["403"]["content"][PROBLEM_MEDIA_TYPE]
    assert "examples" not in media  # one schema renders fine; no dropdown needed


def test_only_route_referenced_types_are_documented():
    app = FastAPI()

    @app.get("/c", responses=problems(Charged))
    async def c() -> dict:
        return {}

    schemas = _openapi(app)["components"]["schemas"]
    assert "Charged" in schemas
    # builtins are never auto-pulled into an app that does not use them:
    assert "NotAuthenticated" not in schemas
    assert "Forbidden" not in schemas


def test_canonical_problem_detail_base_is_documented():
    app = FastAPI()

    @app.get("/c", responses=problems(Charged))
    async def c() -> dict:
        return {}

    assert "ProblemDetail" in _openapi(app)["components"]["schemas"]


def test_wire_schema_pins_type_and_status_as_const():
    app = FastAPI()

    @app.get("/c", responses=problems(Charged))
    async def c() -> dict:
        return {}

    props = _openapi(app)["components"]["schemas"]["Charged"]["properties"]
    assert props["type"]["const"] == "/problems/charged"
    assert props["status"]["const"] == 403


def test_wire_schema_forbids_unknown_members():
    app = FastAPI()

    @app.get("/c", responses=problems(Charged))
    async def c() -> dict:
        return {}

    charged = _openapi(app)["components"]["schemas"]["Charged"]
    assert charged.get("additionalProperties", False) is False
    # ...but the open generic base keeps extensions open:
    detail = _openapi(app)["components"]["schemas"]["ProblemDetail"]
    assert detail.get("additionalProperties") is True


def test_auto_validation_response_uses_problem_media_type():
    app = FastAPI()

    @app.get("/s")
    async def s(limit: Annotated[int, Query(ge=1)] = 10) -> dict:
        return {}

    doc = _openapi(app)
    resp = doc["paths"]["/s"]["get"]["responses"]["422"]
    assert list(resp["content"]) == [PROBLEM_MEDIA_TYPE]
    assert resp["content"][PROBLEM_MEDIA_TYPE]["schema"] == {
        "$ref": "#/components/schemas/ValidationProblem"
    }
    schemas = doc["components"]["schemas"]
    assert "ValidationProblem" in schemas
    assert "InvalidParam" in schemas  # nested $def lifted into components
    # the default FastAPI validation components are pruned once unreferenced:
    assert "HTTPValidationError" not in schemas


def test_duplicate_type_uri_detected_at_build_time():
    class DupeA(Problem):
        type = "/problems/dupe"
        title = "A"
        status = 400

    def _make_b() -> type[Problem]:
        class DupeB(Problem):
            type = "/problems/dupe"
            title = "B"
            status = 400

        return DupeB

    DupeB = _make_b()
    app = FastAPI()

    @app.get("/a", responses=problems(DupeA))
    async def a() -> dict:
        return {}

    @app.get("/b", responses=problems(DupeB))
    async def b() -> dict:
        return {}

    register_problem_components(app)
    with pytest.raises(ValueError, match=r"[Dd]uplicate"):
        app.openapi()


def test_no_dangling_refs():
    app = FastAPI()

    @app.get("/c", responses=problems(Charged))
    async def c() -> dict:
        return {}

    @app.get("/s")
    async def s(limit: Annotated[int, Query(ge=1)] = 10) -> dict:
        return {}

    doc = _openapi(app)
    schemas = doc["components"]["schemas"]
    refs = re.findall(r'"#/components/schemas/([^"]+)"', json.dumps(doc))
    assert all(name in schemas for name in refs), [r for r in refs if r not in schemas]


def test_register_components_preserves_app_metadata():
    app = FastAPI(title="My API", version="9.9.9", servers=[{"url": "https://api.example.com"}])

    @app.get("/c", responses=problems(Charged))
    async def c() -> dict:
        return {}

    doc = _openapi(app)
    assert doc["servers"] == [{"url": "https://api.example.com"}]
    assert doc["info"]["title"] == "My API"
    assert doc["info"]["version"] == "9.9.9"


# --- routes reached through include_router (FastAPI >= 0.137 nests them under an
# --- _IncludedRouter wrapper rather than flattening onto app.routes; issue #10).


def test_included_router_response_uses_problem_media_type():
    router = APIRouter()

    @router.get("/c", responses=problems(Charged))
    async def c() -> dict:
        return {}

    app = FastAPI()
    app.include_router(router)

    resp = _openapi(app)["paths"]["/c"]["get"]["responses"]["403"]
    assert list(resp["content"]) == [PROBLEM_MEDIA_TYPE]
    assert resp["content"][PROBLEM_MEDIA_TYPE]["schema"] == {"$ref": "#/components/schemas/Charged"}


def test_included_router_with_prefix_rewrites_the_prefixed_path():
    router = APIRouter()

    @router.get("/c", responses=problems(Charged))
    async def c() -> dict:
        return {}

    app = FastAPI()
    app.include_router(router, prefix="/api")

    resp = _openapi(app)["paths"]["/api/c"]["get"]["responses"]["403"]
    assert list(resp["content"]) == [PROBLEM_MEDIA_TYPE]


def test_nested_included_routers_response_uses_problem_media_type():
    inner = APIRouter()

    @inner.get("/c", responses=problems(Charged))
    async def c() -> dict:
        return {}

    outer = APIRouter()
    outer.include_router(inner, prefix="/inner")

    app = FastAPI()
    app.include_router(outer, prefix="/api")

    resp = _openapi(app)["paths"]["/api/inner/c"]["get"]["responses"]["403"]
    assert list(resp["content"]) == [PROBLEM_MEDIA_TYPE]


def test_route_problem_types_discovers_types_on_included_router():
    router = APIRouter()

    @router.get("/c", responses=problems(Charged))
    async def c() -> dict:
        return {}

    app = FastAPI()
    app.include_router(router, prefix="/api")

    assert Charged in route_problem_types(app)
