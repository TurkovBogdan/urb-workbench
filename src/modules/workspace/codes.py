"""Workspace codes: generation, the presentation prefix and its removal.

The same technique as ``tasks.codes`` and ``research.codes``: the stored code is a **bare hex
hash** of length ``CODE_LEN``, and the type word (``WORKSPACE@``) is added at the boundary and
stripped on input. A copy of the machinery lives here rather than in a shared core module for
the same reason the neighbours have theirs: code length and the prefix set are properties of the
module, and a generator shared by all would tie them together at the first divergence.

On the way out a code carries the prefix only in JSON (``prefixed``); the internal
``model_dump()`` stays bare. On the way in ``bare_code`` checks the prefix is the right one: a
code of a foreign type (``TASKGROUP@`` where a workspace is expected) is a mixed-up argument, not a
missing row, and the refusal names both types.

**A code is upper case, whole.** It is generated, stored and returned that way, and every code
that comes in is folded to upper case before it reaches SQL — so a lower-case code from before
the switch (a client config, a link in a text) still finds its row. The comparison in the
database is case-sensitive on both providers; the fold here is what makes the case not matter.
"""

from __future__ import annotations

from typing import Annotated

from pydantic import PlainSerializer

from src.core.utils.hashing import random_hash
from src.modules.workspace.constants import CODE_LEN


def new_code() -> str:
    """A new workspace code — a bare ``CODE_LEN``-hex ``random_hash``, upper case."""
    return random_hash(CODE_LEN).upper()


def code_prefix(value: str) -> str:
    """The type word of an input code (``WORKSPACE`` from ``workspace@<hash>``); ``""`` — bare."""
    return value.split("@", 1)[0].upper() if "@" in value else ""


def strip_prefix(value: str | None) -> str | None:
    """Boundary → store: strip the presentation prefix, leaving the bare hash in upper case.

    Idempotent on a bare code (a hex hash has no ``@`` → only the case is folded).
    """
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


__all__ = [
    "bare_code",
    "code_prefix",
    "new_code",
    "prefixed",
    "strip_prefix",
    "tagged",
]
