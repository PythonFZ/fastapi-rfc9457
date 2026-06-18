"""Runnable demo: uv run uvicorn main:app --reload"""

from __future__ import annotations

from typing import Annotated

from fastapi import FastAPI, Query

from fastapi_rfc9457 import (
    NotAuthenticated,
    Problem,
    add_problem_handlers,
    get_problem_docs_router,
    problems,
)


class PostNotFound(Problem):
    """The requested post does not exist."""

    type = "/problems/post-not-found"
    title = "Post Not Found"
    status = 404


class OutOfCredit(Problem):
    """The account does not have enough credit to be charged."""

    type = "/problems/out-of-credit"
    title = "Out of Credit"
    status = 403
    balance: int  # typed extension members, checked at the raise site
    accounts: list[str]


class AccountSuspended(Problem):
    """The account is suspended and cannot be charged."""

    type = "/problems/account-suspended"
    title = "Account Suspended"
    status = 403


app = FastAPI(title="fastapi-rfc9457 demo")
add_problem_handlers(app)  # error handlers + problem+json OpenAPI
app.include_router(get_problem_docs_router(), prefix="/problems")  # dereferenceable type URIs


@app.get("/posts/{post_id}", responses=problems(PostNotFound))
async def get_post(post_id: str) -> dict:
    if post_id != "1":
        raise PostNotFound(detail=f"Post {post_id} not found")
    return {"id": "1", "title": "Hello"}


@app.get("/search")
async def search(limit: Annotated[int, Query(ge=1, le=100)] = 10) -> dict:
    return {"limit": limit}  # try ?limit=abc for a structured 422


# One endpoint, several failure modes. NotAuthenticated is a 401; OutOfCredit and
# AccountSuspended are both 403, so OpenAPI groups them as a `oneOf` union and
# Swagger lists both under the 403 "Examples" dropdown.
@app.get("/charge", responses=problems(NotAuthenticated, OutOfCredit, AccountSuspended))
async def charge(token: str | None = None) -> dict:
    if token is None:
        raise NotAuthenticated(detail="Log in to charge this account.")
    raise OutOfCredit(detail="Not enough credit.", balance=30, accounts=["/accounts/12"])
