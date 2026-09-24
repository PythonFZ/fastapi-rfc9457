from contextlib import asynccontextmanager

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from fastapi_rfc9457.integration import problem_details_lifespan
from fastapi_rfc9457.problem import Problem


def test_lifespan_is_deprecated_and_still_composes():
    events: list[str] = []

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        with pytest.warns(DeprecationWarning, match="validated when defined"):
            cm = problem_details_lifespan(app)
        async with cm:
            events.append("ours-start")
            yield

    with TestClient(FastAPI(lifespan=lifespan)):
        pass

    assert events == ["ours-start"]


def test_missing_status_raises_when_the_class_is_defined():
    with pytest.raises(TypeError, match="Broken is missing a status"):

        class Broken(Problem):
            title = "Broken"


def test_missing_title_raises_when_the_class_is_defined():
    with pytest.raises(TypeError, match="Broken is missing a title"):

        class Broken(Problem):
            status = 500


def test_abstract_base_needs_no_title_or_status():
    class Base(Problem, abstract=True):
        pass

    assert Base._abstract
