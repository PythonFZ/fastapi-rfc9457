"""FastAPI server integration — needs the ``server`` extra."""

from __future__ import annotations

import importlib.util

if importlib.util.find_spec("fastapi") is None:
    raise ModuleNotFoundError(
        "fastapi-rfc9457 server features need FastAPI — install fastapi-rfc9457[server]"
    )

from .docs import get_problem_docs_router
from .integration import add_problem_handlers, problem_details_lifespan
from .openapi import problems

__all__ = [
    "add_problem_handlers",
    "get_problem_docs_router",
    "problem_details_lifespan",
    "problems",
]
