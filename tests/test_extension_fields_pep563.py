from __future__ import annotations

from fastapi_rfc9457.problem import Problem, extension_fields


class FutureProblem(Problem):
    """Defined in a module using PEP 563 future annotations."""

    title = "Future"
    status = 400
    balance: int
    accounts: list[str]


def test_extension_fields_resolves_real_types_under_pep563():
    ef = extension_fields(FutureProblem)
    assert ef == {"balance": int, "accounts": list[str]}
    # the bug returned annotation strings; ensure none are strings
    assert all(not isinstance(value, str) for value in ef.values())
