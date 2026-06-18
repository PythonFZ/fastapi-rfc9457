from example.main import app
from fastapi.testclient import TestClient

from fastapi_rfc9457.models import PROBLEM_MEDIA_TYPE, ProblemDetail

client = TestClient(app)


def test_post_not_found_is_404_problem_json():
    r = client.get("/posts/999")
    assert r.status_code == 404
    assert r.headers["content-type"] == PROBLEM_MEDIA_TYPE
    problem = ProblemDetail.model_validate(r.json())
    assert problem.type == "/problems/post-not-found"
    assert problem.instance == "/posts/999"


def test_search_invalid_query_is_422_with_errors():
    r = client.get("/search?limit=abc")
    assert r.status_code == 422
    errors = ProblemDetail.model_validate(r.json()).model_dump()["errors"]
    assert errors[0]["loc"] == ["query", "limit"]


def test_charge_requires_auth_then_is_403_with_typed_extras():
    unauth = client.get("/charge")  # no token -> NotAuthenticated
    assert unauth.status_code == 401
    # Resolved against the docs router mounted at /problems, so it dereferences.
    assert ProblemDetail.model_validate(unauth.json()).type == "/problems/not-authenticated"

    r = client.get("/charge?token=abc")
    assert r.status_code == 403
    extras = ProblemDetail.model_validate(r.json()).model_dump()
    assert extras["balance"] == 30
    assert extras["accounts"] == ["/accounts/12"]


def test_docs_page_dereferences_type():
    r = client.get("/problems/out-of-credit", headers={"accept": "application/json"})
    assert r.status_code == 200
    assert r.json()["title"] == "Out of Credit"


def test_openapi_documents_only_the_apps_own_types():
    schemas = set(client.get("/openapi.json").json()["components"]["schemas"])
    # NotAuthenticated is a builtin the app *does* use (on /charge), so it belongs.
    assert {
        "ProblemDetail",
        "PostNotFound",
        "OutOfCredit",
        "AccountSuspended",
        "NotAuthenticated",
    } <= schemas
    # builtins the app never uses do not leak into its docs:
    assert "Forbidden" not in schemas
    assert "Conflict" not in schemas


def test_charge_documents_a_oneof_union_under_problem_json():
    doc = client.get("/openapi.json").json()
    schema = doc["paths"]["/charge"]["get"]["responses"]["403"]["content"][PROBLEM_MEDIA_TYPE][
        "schema"
    ]
    assert schema == {
        "oneOf": [
            {"$ref": "#/components/schemas/OutOfCredit"},
            {"$ref": "#/components/schemas/AccountSuspended"},
        ]
    }


def test_search_422_documented_as_problem_json():
    doc = client.get("/openapi.json").json()
    resp = doc["paths"]["/search"]["get"]["responses"]["422"]
    assert list(resp["content"]) == [PROBLEM_MEDIA_TYPE]
    assert resp["content"][PROBLEM_MEDIA_TYPE]["schema"] == {
        "$ref": "#/components/schemas/ValidationProblem"
    }
