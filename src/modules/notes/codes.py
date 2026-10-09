"""Note codes: generation, the presentation prefix and its removal.

The same technique as ``workspace.codes`` and ``tasks.codes``, in a copy of its own: the module
depends on nobody, so it cannot import theirs. The stored code is a **bare hex hash** of length
``CODE_LEN`` in upper case; ``NOTE@`` is added at the boundary and stripped on input, and every
incoming code is folded to upper case before it reaches SQL. A code of a foreign type is a
mixed-up argument, not a missing row, and the refusal names both types.
"""

from __future__ import annotations

from typing import Annotated

from pydantic import PlainSerializer

from src.core.utils.hashing import random_hash
from src.modules.notes.constants import CODE_LEN


def new_code() -> str:
    """A new note code — a bare ``CODE_LEN``-hex ``random_hash``, upper case."""
    return random_hash(CODE_LEN).upper()


def code_prefix(value: str) -> str:
    """The type word of an input code (``NOTE`` from ``note@<hash>``); ``""`` — bare."""
    return value.split("@", 1)[0].upper() if "@" in value else ""


def strip_prefix(value: str | None) -> str | None:
    """Boundary → store: the bare hash in upper case; idempotent on a bare code."""
    return value.rpartition("@")[2].upper() if value else value


def bare_code(value: str | None, prefix: str) -> str | None:
    """The bare code of a ``prefix``-type entity; a foreign prefix — a refusal naming both types."""
    if not value:
        return value
    actual = code_prefix(value)
    if actual and actual != prefix:
        raise ValueError(
            f"Code {value!r} is a {actual}@ reference, but a {prefix}@ code is expected here. "
            f"This is a wrong argument, not a missing row — pass the {prefix}@ code of the "
            "entity you mean (or its bare form)."
        )
    return strip_prefix(value)


def tagged(prefix: str, value: str | None) -> str | None:
    """Store → boundary: the presentation form of a bare code; ``None`` → ``None``."""
    return value if value is None else f"{prefix}@{value}"


def prefixed(prefix: str):
    """A ``str`` type whose JSON form carries ``prefix@`` (a bare hash is accepted on input too)."""
    return Annotated[
        str,
        PlainSerializer(
            lambda value: tagged(prefix, value), return_type=str, when_used="json"
        ),
    ]


__all__ = ["bare_code", "code_prefix", "new_code", "prefixed", "strip_prefix", "tagged"]
