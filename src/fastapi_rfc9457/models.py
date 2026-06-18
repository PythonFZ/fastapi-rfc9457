"""The canonical RFC 9457 wire model."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict

PROBLEM_MEDIA_TYPE = "application/problem+json"


class ProblemDetail(BaseModel):
    """Serialized RFC 9457 problem document.

    Unknown extension members are carried verbatim (``extra="allow"``), so this
    one model is both the emitted wire shape and the generic client-parse result.

    Attributes
    ----------
    type : str
        Problem-type URI reference. Defaults to ``"about:blank"`` per RFC 9457.
    title : str
        Short, human-readable summary of the problem type.
    status : int
        HTTP status code generated for this occurrence.
    detail : str | None
        Human-readable explanation specific to this occurrence.
    instance : str | None
        URI reference identifying this specific occurrence.
    """

    model_config = ConfigDict(extra="allow")

    type: str = "about:blank"
    title: str
    status: int
    detail: str | None = None
    instance: str | None = None
