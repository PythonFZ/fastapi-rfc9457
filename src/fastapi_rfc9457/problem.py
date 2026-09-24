"""The ``Problem`` authoring surface: a Pydantic dataclass + ``Exception``."""

from __future__ import annotations

import dataclasses
import re
from collections.abc import Iterator, Mapping
from typing import Any, ClassVar, Self, dataclass_transform, get_type_hints

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

    Pass ``abstract=True`` to define a base that carries shared fields, headers
    or methods for its subclasses: ``class RetryAfter(Problem, abstract=True)``.
    A concrete subclass missing ``title`` or ``status`` raises ``TypeError``
    when it is defined. An abstract type omits them, is skipped by the client
    ``type`` lookup, and raises ``TypeError`` when constructed. Its subclasses
    are concrete.

    Each class declares only its own ``headers``, ``response_headers()`` and
    ``header_examples()``; the library merges them along the MRO, so a type
    built on ``RetryAfter`` sends ``Retry-After`` alongside its own headers.
    A subclass replaces an inherited header value by returning the same name.
    """

    title: ClassVar[str]
    status: ClassVar[int]
    type: ClassVar[str | None] = None
    #: Whether ``type`` was set on the class (vs. derived). An author-written
    #: ``type`` is emitted verbatim; a derived one is resolved against the docs
    #: mount at serialize time (see uris.resolve_type_uri).
    _type_is_explicit: ClassVar[bool] = False
    #: Set per class from the ``abstract`` class keyword; subclasses start concrete.
    _abstract: ClassVar[bool] = False
    #: Response headers this problem type sends, as name -> OpenAPI description,
    #: merged with those declared by its bases.
    headers: ClassVar[Mapping[str, str]] = {}
    detail: str | None = None
    instance: str | None = None

    def __init_subclass__(cls, *, abstract: bool = False, **kwargs) -> None:
        super().__init_subclass__(**kwargs)
        cls._abstract = abstract
        if not abstract:
            for attr in ("title", "status"):
                if not getattr(cls, attr, None):
                    raise TypeError(
                        f"{cls.__name__} is missing a {attr}; set it, or declare "
                        f"`class {cls.__name__}(..., abstract=True)` for a shared base."
                    )
        own_type = cls.__dict__.get("type")
        cls._type_is_explicit = own_type is not None
        if own_type is not None or not abstract:
            cls.type = own_type if own_type is not None else _derive_type(cls.__name__)
        merged = {
            name: description
            for base in reversed(cls.__mro__)
            for name, description in base.__dict__.get("headers", {}).items()
        }
        if "headers" in cls.__dict__ and not cls.__dict__["headers"] and merged:
            raise TypeError(
                f"{cls.__name__}.headers is empty, but headers extend the inherited ones "
                f"({', '.join(map(repr, merged))}); drop the empty declaration."
            )
        cls.headers = merged

    def __new__(cls, *args: Any, **kwargs: Any) -> Self:
        require_concrete(cls)
        return super().__new__(cls, *args, **kwargs)

    def response_headers(self) -> Mapping[str, str]:
        """Return the header values this class adds to the response.

        Override alongside ``headers`` to send headers built from the
        instance's fields; the headers of the bases are merged in.

        Returns
        -------
        Mapping[str, str]
            Header name -> value, a subset of the names declared in ``headers``.
        """
        return {}

    @classmethod
    def header_examples(cls) -> Mapping[str, str]:
        """Return example values for the headers this class adds, for OpenAPI.

        The examples of the bases are merged in.

        Returns
        -------
        Mapping[str, str]
            Header name -> example value, a subset of the names declared in ``headers``.
        """
        return {}

    def __str__(self) -> str:
        """Human-readable representation for logs and traceback tails."""

        head = f"{getattr(self, 'status', '')} {getattr(self, 'title', '')}".strip()
        head = head or type(self).__name__
        return f"{head} — {self.detail}" if self.detail else head


def require_concrete(cls: type[Problem]) -> None:
    """Raise ``TypeError`` when ``cls`` was declared with ``abstract=True``."""
    if cls._abstract:
        raise TypeError(f"{cls.__name__} is abstract; use one of its concrete subclasses.")


def _own_methods(cls: type[Problem], name: str) -> list[Any]:
    return [base.__dict__[name] for base in reversed(cls.__mro__) if name in base.__dict__]


def sent_headers(problem: Problem) -> dict[str, str]:
    """Merge the ``response_headers()`` of every class in the problem's MRO.

    Parameters
    ----------
    problem : Problem
        The raised problem.

    Returns
    -------
    dict[str, str]
        Header name -> value; a subclass's value replaces an inherited one.
    """
    return {
        name: value
        for method in _own_methods(type(problem), "response_headers")
        for name, value in method(problem).items()
    }


def example_headers(cls: type[Problem]) -> dict[str, str]:
    """Merge the ``header_examples()`` of every class in the MRO of ``cls``.

    Parameters
    ----------
    cls : type[Problem]
        The documented problem type.

    Returns
    -------
    dict[str, str]
        Header name -> example value; a subclass's example replaces an inherited one.
    """
    return {
        name: value
        for method in _own_methods(cls, "header_examples")
        for name, value in method.__func__(cls).items()
    }


def iter_problem_types() -> Iterator[type[Problem]]:
    """Yield every defined concrete :class:`Problem` subclass, transitively.

    Walks ``Problem.__subclasses__()`` (Python's own weakly-held subclass list),
    so no explicit registry is kept: a type is "known" exactly while it is a live
    class. Used to map an incoming ``type`` URI back to its authored class and to
    validate the type set at startup.

    Yields
    ------
    type[Problem]
        Each distinct concrete subclass, deduplicated. Abstract types are
        walked for their children and left out.
    """
    seen: set[type[Problem]] = set()
    stack: list[type[Problem]] = list(Problem.__subclasses__())
    while stack:
        cls = stack.pop()
        if cls in seen:
            continue
        seen.add(cls)
        if not cls._abstract:
            yield cls
        stack.extend(cls.__subclasses__())


class UndeclaredHeaderWarning(UserWarning):
    """A problem sent a response header missing from its ``headers`` declaration.

    The header is still sent; the OpenAPI schema lacks it. Promote it to an
    error in tests with ``filterwarnings = ["error::fastapi_rfc9457.UndeclaredHeaderWarning"]``.
    """


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
