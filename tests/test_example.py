from example.main import app
from fastapi.testclient import TestClient

from fastapi_rfc9457.models import PROBLEM_MEDIA_TYPE

client = TestClient(app)


def test_post_not_found_is_404_problem_json():
    r = client.get("/posts/999")
    assert r.status_code == 404
    assert r.headers["content-type"] == PROBLEM_MEDIA_TYPE
    body = r.json()
    assert body["type"] == "/problems/post-not-found"
    assert body["instance"] == "/posts/999"


def test_search_invalid_query_is_422_with_errors():
    r = client.get("/search?limit=abc")
    assert r.status_code == 422
    body = r.json()
    assert body["errors"][0]["loc"] == ["query", "limit"]


def test_charge_is_403_with_typed_extras():
    r = client.get("/charge")
    assert r.status_code == 403
    body = r.json()
    assert body["balance"] == 30
    assert body["accounts"] == ["/accounts/12"]


def test_docs_page_dereferences_type():
    r = client.get("/problems/out-of-credit", headers={"accept": "application/json"})
    assert r.status_code == 200
    assert r.json()["title"] == "Out of Credit"


def test_openapi_lists_problem_schemas():
    doc = client.get("/openapi.json").json()
    keys = set(doc["components"]["schemas"])
    assert {"ProblemDetail", "PostNotFound", "OutOfCredit"} <= keys
