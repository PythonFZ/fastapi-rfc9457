"""The bare install is a lean, fastapi-free client (issue #15).

These run in a fresh interpreter (subprocess) because they assert on what the
*import* pulls in — something the in-process test session, which imports fastapi
everywhere, cannot observe.
"""

from __future__ import annotations

import subprocess
import sys
import textwrap


def _run(code: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-c", textwrap.dedent(code)],
        capture_output=True,
        text=True,
    )


def test_bare_import_pulls_neither_fastapi_nor_starlette():
    result = _run(
        """
        import sys
        import fastapi_rfc9457  # noqa: F401
        assert "fastapi" not in sys.modules, "fastapi imported eagerly on bare install"
        assert "starlette" not in sys.modules, "starlette imported eagerly on bare install"
        """
    )
    assert result.returncode == 0, result.stderr


def test_client_symbols_work_without_fastapi():
    result = _run(
        """
        from fastapi_rfc9457 import NotFound, Problem, parse_problem, raise_for_problem  # noqa: F401
        problem = parse_problem(
            {"type": "not-found", "title": "Not Found", "status": 404}
        )
        assert isinstance(problem, NotFound)
        """
    )
    assert result.returncode == 0, result.stderr


def test_server_import_without_fastapi_is_actionable():
    result = _run(
        """
        import importlib.util
        _real = importlib.util.find_spec
        importlib.util.find_spec = (
            lambda name, *a, **k: None if name == "fastapi" else _real(name, *a, **k)
        )
        try:
            import fastapi_rfc9457.server  # noqa: F401
        except ModuleNotFoundError as exc:
            assert "fastapi-rfc9457[server]" in str(exc), str(exc)
        else:
            raise AssertionError("expected ModuleNotFoundError for missing fastapi")
        """
    )
    assert result.returncode == 0, result.stderr
