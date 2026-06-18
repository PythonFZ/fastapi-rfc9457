"""Runnable demo: uv run uvicorn example.main:app --reload"""

from __future__ import annotations

from typing import Annotated

from fastapi import FastAPI, Query

from fastapi_rfc9457 import (
    Problem,
    add_problem_handlers,
    get_problem_docs_router,
    problems,
)


class PostNotFound(Problem):
    """The requested post does not exist."""

    type = "/problems/post-not-found"
    title = "Not Found"
    status = 404


class OutOfCredit(Problem):
    """The account does not have enough credit."""

    type = "/problems/out-of-credit"
    title = "Out of Credit"
    status = 403
    balance: int
    accounts: list[str]


app = FastAPI(title="fastapi-rfc9457 demo")
add_problem_handlers(app)
app.include_router(get_problem_docs_router(), prefix="/problems", tags=["problems"])


@app.get("/posts/{post_id}", responses=problems(PostNotFound))
async def get_post(post_id: str) -> dict:
    if post_id != "1":
        raise PostNotFound(detail=f"Post {post_id} not found")
    return {"id": "1", "title": "Hello"}


@app.get("/search")
async def search(limit: Annotated[int, Query(ge=1, le=100)] = 10) -> dict:
    return {"limit": limit}


@app.get("/charge", responses=problems(OutOfCredit))
async def charge() -> dict:
    raise OutOfCredit(detail="Not enough credit to charge.", balance=30, accounts=["/accounts/12"])
