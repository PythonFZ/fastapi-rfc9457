from contextlib import asynccontextmanager

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from fastapi_rfc9457.integration import add_problem_handlers, problem_details_lifespan
from fastapi_rfc9457.problem import Problem


def test_lifespan_runs_and_composes_with_user_lifespan():
    events: list[str] = []

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        events.append("user-start")
        async with problem_details_lifespan(app):
            events.append("ours-start")
            yield
        events.append("user-end")

    app = FastAPI(lifespan=lifespan)
    add_problem_handlers(app)

    with TestClient(app):
        pass

    assert events == ["user-start", "ours-start", "user-end"]


def test_lifespan_validates_registry_fails_fast_on_missing_status():
    # A problem type with no `status` ClassVar set.
    class Broken(Problem):
        title = "Broken"
        # no status

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        async with problem_details_lifespan(app):
            yield

    app = FastAPI(lifespan=lifespan)
    with pytest.raises(RuntimeError, match="status"), TestClient(app):
        pass
