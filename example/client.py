"""Client-side demo: the httpx hook turns problem+json back into typed exceptions.

Needs the ``client`` extra::

    uv add fastapi-rfc9457[client]

Start the demo server in one shell::

    cd example && uv run uvicorn main:app

then run this consumer in another::

    uv run client.py
"""

from __future__ import annotations

import os

import httpx
from main import OutOfCredit, PostNotFound

from fastapi_rfc9457 import NotAuthenticated, httpx_raise_hook

DEFAULT_BASE_URL = os.environ.get("DEMO_BASE_URL", "http://localhost:8000")


def demo(base_url: str = DEFAULT_BASE_URL) -> None:
    """Exercise the demo endpoints, letting the hook raise typed problems."""
    with httpx.Client(
        base_url=base_url,
        event_hooks={"response": [httpx_raise_hook()]},
    ) as client:
        print("GET /posts/1   ->", client.get("/posts/1").json())  # 200, hook is a no-op

        try:
            client.get("/posts/999")  # 404 problem+json
        except PostNotFound as exc:
            print("PostNotFound   ->", exc.detail)

        try:
            client.get("/charge", params={"token": "x"})  # 403 problem+json
        except OutOfCredit as exc:
            # extension members round-trip back as real typed attributes
            print("OutOfCredit    ->", f"balance={exc.balance}, accounts={exc.accounts}")

        try:
            client.get("/charge")  # 401 problem+json (a built-in problem type)
        except NotAuthenticated as exc:
            print("NotAuthenticated ->", exc.detail)


if __name__ == "__main__":
    demo()
