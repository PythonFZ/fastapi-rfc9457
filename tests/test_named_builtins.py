from collections.abc import Mapping
from typing import ClassVar

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from fastapi_rfc9457 import InternalServerError, Problem, ValidationProblem
from fastapi_rfc9457.client import raise_for_problem
from fastapi_rfc9457.docs import get_problem_docs_router
from fastapi_rfc9457.integration import add_problem_handlers


class AppError(Exception): ...


class NamedInvalid(ValidationProblem, AppError):
    """The request failed this app's validation."""

    title = "Invalid Request"


class NamedBroken(InternalServerError, AppError):
    """This app broke."""

    title = "Broken"


class AbstractInvalid(ValidationProblem, abstract=True):
    """An abstract validation base."""


class CodedInvalid(ValidationProblem):
    """A validation class declaring a field the 422 handler never writes."""

    code: str


class Teapot(InternalServerError):
    """An internal class answering with another status."""

    status = 418


class TracedInvalid(ValidationProblem):
    headers: ClassVar[Mapping[str, str]] = {"X-Trace": "The trace id."}

    def response_headers(self) -> Mapping[str, str]:
        return {"X-Trace": "t-422"}


class TracedBroken(InternalServerError):
    headers: ClassVar[Mapping[str, str]] = {"X-Trace": "The trace id."}

    def response_headers(self) -> Mapping[str, str]:
        return {"X-Trace": "t-500"}


class HintedInvalid(ValidationProblem):
    hint: str = "See the docs."


class Unrelated(Problem):
    """A problem outside the validation hierarchy."""

    title = "Unrelated"
    status = 422


def build_app(
    *,
    docs: bool = False,
    validation: type[ValidationProblem] = NamedInvalid,
    internal: type[InternalServerError] = NamedBroken,
) -> FastAPI:
    app = FastAPI()
    add_problem_handlers(app, validation=validation, internal=internal)
    if docs:
        app.include_router(get_problem_docs_router(), prefix="/problems")

    @app.get("/items/{item_id}")
    async def get_item(item_id: int) -> dict:
        return {"id": item_id}

    @app.get("/boom")
    async def boom() -> dict:
        raise RuntimeError("kaput")

    return app


def test_422_carries_the_named_validation_class():
    r = TestClient(build_app()).get("/items/abc")
    body = r.json()
    assert r.status_code == 422
    assert body["type"] == "named-invalid"
    assert body["title"] == "Invalid Request"
    assert body["status"] == 422
    assert body["errors"][0]["loc"] == ["path", "item_id"]


def test_500_carries_the_named_internal_class():
    client = TestClient(build_app(), raise_server_exceptions=False)
    body = client.get("/boom").json()
    assert body["type"] == "named-broken"
    assert body["title"] == "Broken"
    assert body["status"] == 500


def test_422_sends_the_named_class_headers():
    r = TestClient(build_app(validation=TracedInvalid)).get("/items/abc")
    assert r.status_code == 422
    assert r.headers["x-trace"] == "t-422"


def test_500_sends_the_named_class_headers():
    client = TestClient(build_app(internal=TracedBroken), raise_server_exceptions=False)
    r = client.get("/boom")
    assert r.status_code == 500
    assert r.headers["x-trace"] == "t-500"


def test_422_carries_a_defaulted_extension_field():
    body = TestClient(build_app(validation=HintedInvalid)).get("/items/abc").json()
    assert body["hint"] == "See the docs."
    assert body["errors"][0]["loc"] == ["path", "item_id"]


def test_client_raises_the_named_validation_class():
    r = TestClient(build_app()).get("/items/abc")
    with pytest.raises(NamedInvalid) as caught:
        raise_for_problem(r)
    assert isinstance(caught.value, AppError)
    assert caught.value.errors[0].loc == ["path", "item_id"]


def test_client_raises_the_named_internal_class():
    r = TestClient(build_app(), raise_server_exceptions=False).get("/boom")
    with pytest.raises(NamedBroken):
        raise_for_problem(r)


def test_openapi_422_references_the_named_validation_class():
    doc = TestClient(build_app(docs=True)).get("/openapi.json").json()
    content = doc["paths"]["/items/{item_id}"]["get"]["responses"]["422"]["content"]
    ref = content["application/problem+json"]["schema"]["$ref"]
    assert ref == "#/components/schemas/NamedInvalid"
    schemas = doc["components"]["schemas"]
    assert "ValidationProblem" not in schemas
    assert schemas["NamedInvalid"]["properties"]["type"]["const"] == "/problems/named-invalid"


def test_docs_page_serves_the_named_classes():
    client = TestClient(build_app(docs=True))
    headers = {"accept": "application/json"}
    assert client.get("/problems/named-invalid", headers=headers).json()["title"] == (
        "Invalid Request"
    )
    assert client.get("/problems/named-broken", headers=headers).json()["title"] == "Broken"
    assert client.get("/problems/validation").status_code == 404
    assert client.get("/problems/internal-server-error").status_code == 404


def test_defaults_answer_with_the_builtin_classes():
    app = FastAPI()
    add_problem_handlers(app)

    @app.get("/items/{item_id}")
    async def get_item(item_id: int) -> dict:
        return {"id": item_id}

    body = TestClient(app).get("/items/abc").json()
    assert body["type"] == "validation"
    assert body["title"] == ValidationProblem.title


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        ({"validation": Unrelated}, "subclass of ValidationProblem"),
        ({"internal": NamedInvalid}, "subclass of InternalServerError"),
        ({"validation": AbstractInvalid}, "abstract"),
        ({"validation": CodedInvalid}, "code"),
        ({"internal": Teapot}, "status 500"),
    ],
)
def test_rejects_a_class_the_handler_cannot_answer_with(kwargs, message):
    with pytest.raises(TypeError, match=message):
        add_problem_handlers(FastAPI(), **kwargs)
