import fastapi_rfc9457 as pkg
from fastapi_rfc9457 import server


def test_version_is_a_nonempty_string():
    assert isinstance(pkg.__version__, str)
    assert pkg.__version__


def test_client_symbols_are_exported():
    expected = {
        "Problem",
        "ProblemDetail",
        "ProblemError",
        "parse_problem",
        "raise_for_problem",
        "httpx_raise_hook",
        "BadRequest",
        "NotAuthenticated",
        "Forbidden",
        "NotFound",
        "Conflict",
        "UnprocessableContent",
        "TooManyRequests",
        "InternalServerError",
        "ValidationProblem",
        "InvalidParam",
    }
    for name in expected:
        assert hasattr(pkg, name), name
    assert expected <= set(pkg.__all__)


def test_server_symbols_are_exported():
    expected = {
        "add_problem_handlers",
        "problem_details_lifespan",
        "get_problem_docs_router",
        "problems",
    }
    for name in expected:
        assert hasattr(server, name), name
    assert expected <= set(server.__all__)
