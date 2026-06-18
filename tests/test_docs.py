from fastapi import FastAPI
from fastapi.testclient import TestClient

from fastapi_rfc9457.docs import get_problem_docs_router
from fastapi_rfc9457.problem import Problem


class DocOutOfCredit(Problem):
    """The account does not have enough credit."""

    type = "/problems/doc-out-of-credit"
    title = "Out of Credit"
    status = 403
    balance: int


def build_app() -> FastAPI:
    app = FastAPI()
    app.include_router(
        get_problem_docs_router(DocOutOfCredit), prefix="/problems", tags=["problems"]
    )
    return app


def test_json_doc_page():
    client = TestClient(build_app())
    r = client.get("/problems/doc-out-of-credit", headers={"accept": "application/json"})
    assert r.status_code == 200
    body = r.json()
    assert body["type"] == "/problems/doc-out-of-credit"
    assert body["title"] == "Out of Credit"
    assert body["status"] == 403
    assert "enough credit" in body["description"]
    assert "balance" in body["extensions"]


def test_html_doc_page():
    client = TestClient(build_app())
    r = client.get("/problems/doc-out-of-credit", headers={"accept": "text/html"})
    assert r.status_code == 200
    assert "text/html" in r.headers["content-type"]
    assert "Out of Credit" in r.text


def test_route_path_is_type_uri_last_segment():
    # mounted at /problems, type ends with /doc-out-of-credit -> /problems/doc-out-of-credit
    client = TestClient(build_app())
    assert client.get("/problems/doc-out-of-credit").status_code == 200
