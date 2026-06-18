from fastapi import FastAPI
from fastapi.testclient import TestClient

from fastapi_rfc9457.builtins import ValidationProblem
from fastapi_rfc9457.models import PROBLEM_MEDIA_TYPE
from fastapi_rfc9457.openapi import problems, register_problem_components
from fastapi_rfc9457.problem import Problem


class AlphaGone(Problem):
    """Alpha is gone."""

    title = "Gone"
    status = 410


class BetaGone(Problem):
    """Beta is gone."""

    title = "Gone"
    status = 410


class Charged(Problem):
    """Charged."""

    title = "Out of Credit"
    status = 403


def test_problems_single_type_uses_ref_under_problem_json():
    resp = problems(Charged)
    assert set(resp) == {403}
    schema = resp[403]["content"][PROBLEM_MEDIA_TYPE]["schema"]
    assert schema == {"$ref": "#/components/schemas/Charged"}


def test_problems_merges_two_types_at_same_status_with_oneof():
    resp = problems(AlphaGone, BetaGone)
    schema = resp[410]["content"][PROBLEM_MEDIA_TYPE]["schema"]
    assert schema == {
        "oneOf": [
            {"$ref": "#/components/schemas/AlphaGone"},
            {"$ref": "#/components/schemas/BetaGone"},
        ]
    }
    assert "Alpha is gone." in resp[410]["description"]
    assert "Beta is gone." in resp[410]["description"]


def test_problems_different_statuses_merge_cleanly():
    resp = problems(Charged, AlphaGone)
    assert set(resp) == {403, 410}


def test_register_components_injects_schemas_and_no_dangling_refs():
    app = FastAPI()

    @app.get("/c", responses=problems(Charged))
    async def c() -> dict:
        return {}

    @app.get("/v", responses=problems(ValidationProblem))
    async def v() -> dict:
        return {}

    register_problem_components(app)
    doc = TestClient(app).get("/openapi.json").json()

    schemas = doc["components"]["schemas"]
    assert "ProblemDetail" in schemas
    assert "Charged" in schemas
    assert "ValidationProblem" in schemas
    # nested $defs lifted into components.schemas (no dangling ref):
    assert "InvalidParam" in schemas

    # route documents problem+json only, with a $ref:
    route = doc["paths"]["/c"]["get"]["responses"]["403"]["content"]
    assert list(route) == [PROBLEM_MEDIA_TYPE]
    assert route[PROBLEM_MEDIA_TYPE]["schema"] == {"$ref": "#/components/schemas/Charged"}

    # every local $ref resolves to a present component:
    import json
    import re

    refs = re.findall(r'"#/components/schemas/([^"]+)"', json.dumps(doc))
    assert all(name in schemas for name in refs)
