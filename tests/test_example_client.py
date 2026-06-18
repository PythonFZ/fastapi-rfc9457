import os
import socket
import subprocess
import threading
import time
from pathlib import Path

import pytest
import uvicorn
from example.main import app

EXAMPLE_DIR = Path(__file__).resolve().parent.parent / "example"


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


class _ThreadedServer(uvicorn.Server):
    """A uvicorn server runnable from a background thread (signals need the main thread)."""

    def install_signal_handlers(self) -> None:
        pass


@pytest.fixture(scope="module")
def base_url():
    port = _free_port()
    config = uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning")
    server = _ThreadedServer(config)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    deadline = time.monotonic() + 5
    while not server.started:
        if time.monotonic() > deadline:
            raise RuntimeError("uvicorn did not start in time")
        time.sleep(0.01)
    try:
        yield f"http://127.0.0.1:{port}"
    finally:
        server.should_exit = True
        thread.join()


@pytest.fixture(scope="module")
def client_output(base_url):
    """Run the example client exactly as documented, pointed at the live demo server."""
    result = subprocess.run(
        ["uv", "run", "client.py"],
        cwd=EXAMPLE_DIR,
        env={**os.environ, "DEMO_BASE_URL": base_url},
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert result.returncode == 0, result.stderr
    return result.stdout


# The exact block documented in example/README.md — the hook turns each
# problem+json reply back into its typed exception (note OutOfCredit's typed
# extension members surviving the round-trip).
EXPECTED_OUTPUT = (
    "GET /posts/1   -> {'id': '1', 'title': 'Hello'}\n"
    "PostNotFound   -> Post 999 not found\n"
    "OutOfCredit    -> balance=30, accounts=['/accounts/12']\n"
    "NotAuthenticated -> Log in to charge this account.\n"
)


def test_client_script_prints_the_documented_typed_problems(client_output):
    assert client_output == EXPECTED_OUTPUT
