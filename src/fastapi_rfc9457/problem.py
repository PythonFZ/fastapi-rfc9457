"""The ``Problem`` authoring surface: a Pydantic dataclass + ``Exception``."""

from __future__ import annotations

import dataclasses
import re
from collections.abc import Iterator
from typing import ClassVar, dataclass_transform, get_type_hints

import pydantic

from .models import ProblemDetail

_STANDARD_FIELDS = frozenset({"detail", "instance"})


def _derive_type(name: str) -> str:
    """Derive a kebab-case type id from a class name.

    A trailing ``Problem`` or ``Error`` is stripped, then the CamelCase name is
    lower-kebab-cased. ``OutOfCredit`` -> ``"out-of-credit"``.

    Parameters
    ----------
    name : str
        The class ``__name__``.

    Returns
    -------
    str
        The derived relative type-URI reference (RFC 9457 §3.1.1 permits these).

    Notes
    -----
    Derivation is lossy for acronym-heavy names (``HTTPError`` -> ``"http"``);
    set an explicit ``type`` ClassVar when the derived id would be ambiguous.
    """
    base = re.sub(r"(Problem|Error)$", "", name) or name
    step = re.sub(r"(.)([A-Z][a-z]+)", r"\1-\2", base)
    return re.sub(r"([a-z0-9])([A-Z])", r"\1-\2", step).lower()


def extension_fields(cls: type) -> dict[str, type]:
    """Return the typed extension members of a problem class.

    Annotations are resolved with :func:`typing.get_type_hints` so that string
    annotations (PEP 563 / ``from __future__ import annotations``) come back as
    real types rather than strings.

    Parameters
    ----------
    cls : type
        A ``Problem`` subclass.

    Returns
    -------
    dict[str, type]
        Field name -> resolved annotation, excluding the standard
        ``detail``/``instance`` members.
    """
    hints = get_type_hints(cls)
    return {
        field.name: hints[field.name]
        for field in dataclasses.fields(cls)
        if field.name not in _STANDARD_FIELDS
    }


@dataclass_transform(kw_only_default=True)
class _ProblemMeta(type):
    """Metaclass that makes ``Problem`` and every subclass a kw-only dataclass.

    The ``@dataclass_transform`` decoration tells static checkers to treat each
    subclass as a dataclass (so field declarations become kw-only, type-checked
    constructor parameters); ``__new__`` applies the runtime transform.

    The transform is configured ``extra="forbid"`` so an unknown constructor
    keyword — a typo, or an attempt to pass a ``ClassVar`` constant such as
    ``status=404`` — raises rather than being silently dropped.
    """

    def __new__(
        mcs,
        name: str,
        bases: tuple[type, ...],
        namespace: dict[str, object],
        **kwargs: object,
    ):
        cls = super().__new__(mcs, name, bases, namespace, **kwargs)
        config = pydantic.ConfigDict(extra="forbid")
        return pydantic.dataclasses.dataclass(config=config, kw_only=True, frozen=False, eq=False)(
            cls
        )


class Problem(Exception, metaclass=_ProblemMeta):
    """Base class for authored RFC 9457 problem types.

    Subclasses declare ``title``/``status`` (and optionally ``type``) as plain
    class attributes — they are ``ClassVar`` constants, not fields — and declare
    extension members as annotated fields. Raise instances directly.

    Notes
    -----
    No decorator is needed on subclasses: the metaclass carries the dataclass
    machinery. Instances are not frozen (a ``Problem`` is an ``Exception``, which
    CPython must be able to write ``__traceback__`` to as it unwinds); the
    handlers never mutate a raised problem, so reusing a module-level constant
    stays safe. Unknown constructor keywords are rejected (``extra="forbid"``):
    passing a ``ClassVar`` constant like ``status=404`` raises rather than being
    ignored.
    """

    title: ClassVar[str]
    status: ClassVar[int]
    type: ClassVar[str | None] = None
    #: Whether ``type`` was set on the class (vs. derived). An author-written
    #: ``type`` is emitted verbatim; a derived one is resolved against the docs
    #: mount at serialize time (see uris.resolve_type_uri).
    _type_is_explicit: ClassVar[bool] = False
    detail: str | None = None
    instance: str | None = None

    def __init_subclass__(cls, **kwargs) -> None:
        super().__init_subclass__(**kwargs)
        cls._type_is_explicit = cls.__dict__.get("type") is not None
        cls.type = cls.type if cls.type is not None else _derive_type(cls.__name__)


def iter_problem_types() -> Iterator[type[Problem]]:
    """Yield every defined :class:`Problem` subclass, transitively.

    Walks ``Problem.__subclasses__()`` (Python's own weakly-held subclass list),
    so no explicit registry is kept: a type is "known" exactly while it is a live
    class. Used to map an incoming ``type`` URI back to its authored class and to
    validate the type set at startup.

    Yields
    ------
    type[Problem]
        Each distinct subclass, deduplicated.
    """
    seen: set[type[Problem]] = set()
    stack: list[type[Problem]] = list(Problem.__subclasses__())
    while stack:
        cls = stack.pop()
        if cls in seen:
            continue
        seen.add(cls)
        yield cls
        stack.extend(cls.__subclasses__())


class ProblemError(Exception):
    """Client-side fallback for a problem response whose ``type`` isn't registered.

    Parameters
    ----------
    problem : ProblemDetail
        The parsed wire model.
    """

    def __init__(self, problem: ProblemDetail) -> None:
        self.problem = problem
        super().__init__(f"{problem.status} {problem.title}")
