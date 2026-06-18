import json
import shutil
import subprocess

import pytest


def _run_pyright(path: str, *, ignore_project: bool = False) -> list[dict]:
    cmd = ["uv", "run", "pyright", "--outputjson"]
    if ignore_project:
        # Use /dev/null as the project file so pyright doesn't apply
        # pyproject.toml's exclude list (which would skip expected_errors.py).
        cmd += ["--project", "/dev/null"]
    cmd.append(path)
    out = subprocess.run(cmd, capture_output=True, text=True)
    # pyright exits non-zero when diagnostics exist; that's expected here.
    return json.loads(out.stdout)["generalDiagnostics"]


@pytest.mark.skipif(shutil.which("uv") is None, reason="uv required")
def test_expected_errors_are_reported():
    diags = _run_pyright("tests/static/expected_errors.py", ignore_project=True)
    rules = {d.get("rule") for d in diags if d.get("rule")}
    assert "reportCallIssue" in rules  # missing required extension members
    assert "reportArgumentType" in rules  # wrong extension-member type
    assert "reportAssignmentType" in rules  # wrong ClassVar type


@pytest.mark.skipif(shutil.which("uv") is None, reason="uv required")
def test_valid_usage_has_no_errors():
    diags = _run_pyright("tests/static/valid_usage.py")
    errors = [d for d in diags if d.get("severity") == "error"]
    assert errors == [], errors
