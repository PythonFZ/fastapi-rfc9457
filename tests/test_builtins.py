from fastapi_rfc9457.builtins import (
    BadRequest,
    Conflict,
    Forbidden,
    InternalServerError,
    InvalidParam,
    NotAuthenticated,
    NotFound,
    TooManyRequests,
    UnprocessableContent,
    ValidationProblem,
)
from fastapi_rfc9457.problem import Problem, extension_fields


def test_builtin_statuses():
    assert BadRequest.status == 400
    assert NotAuthenticated.status == 401
    assert Forbidden.status == 403
    assert NotFound.status == 404
    assert Conflict.status == 409
    assert UnprocessableContent.status == 422
    assert TooManyRequests.status == 429
    assert InternalServerError.status == 500


def test_builtins_are_problem_subclasses_with_no_extension_fields():
    assert issubclass(NotFound, Problem)
    assert extension_fields(NotFound) == {}


def test_builtins_are_raisable():
    err = NotFound(detail="gone")
    assert isinstance(err, Exception)
    assert err.detail == "gone"


def test_validation_problem_shape():
    assert ValidationProblem.status == 422
    assert ValidationProblem.type == "/problems/validation"
    assert extension_fields(ValidationProblem) == {"errors": list[InvalidParam]}


def test_invalid_param_fields():
    p = InvalidParam(loc=["body", 0, "x"], detail="Field required", type="missing")
    assert p.pointer is None
    assert p.input is None
    dumped = p.model_dump(exclude_none=True)
    assert dumped == {"loc": ["body", 0, "x"], "detail": "Field required", "type": "missing"}
