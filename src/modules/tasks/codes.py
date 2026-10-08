"""``tasks`` entity codes: generation, the presentation prefix, and stripping it.

The stored code (the PK and every FK in the module) is a **bare hex hash** of length
``CODE_LEN``, as ``random_hash`` returns it. The type prefix (``WORKSPACE@`` / ``TASKGROUP@`` /
``TASK@``) is **presentation**: it lets the person and the agent tell one entity from another at
a glance and turns a free-floating code into a typed reference. The wire form is ``type@hash``:
``@`` reads as "reference in a namespace" and never occurs in the hex alphabet.

The prefix lives ONLY at the boundary and never reaches the database:

- **outbound** (DTO → agent / API): a field annotated ``prefixed(PREFIX)`` is serialized with
  the prefix, and only in JSON — the internal ``model_dump()`` stays bare;
- **inbound** (agent / API → CRUD): ``bare_code`` strips the prefix before the value reaches
  SQL.

Since the hash alphabet is hex (no ``@`` in it), ``strip_prefix`` is idempotent on an already
bare code: applying it to internal values is safe.

**A code is upper case, whole** — prefix and hash: ``TASK@3F9A0C21BE``. It is generated, stored
and returned that way, and every incoming code is folded to upper case on the way in, prefix
included — so a lower-case code from before the switch (in a client config, a journal entry, a link in a
body) still finds its row. The database compares case-sensitively on both providers; the fold
here is what makes the case not matter. The rows written before the switch were converted by
``tsm_007_codes_upper``.

``bare_code`` also checks that the prefix is **the right one**. A code of another type
(``TASKGROUP@`` where a task is expected) is not "not found" but a mixed-up argument; the refusal
names both types, and the agent fixes the call on the first try instead of concluding the row
was deleted. A retired type word (``GROUP@``, see ``LEGACY_CODE_PREFIXES``) is read as its
current one, so codes quoted before a rename keep resolving.
"""

from __future__ import annotations

from typing import Annotated

from pydantic import PlainSerializer

from src.core.utils.hashing import random_hash
from src.modules.tasks.constants import CODE_LEN, LEGACY_CODE_PREFIXES


def new_code() -> str:
    """A new entity code — a bare ``CODE_LEN``-hex ``random_hash``, upper case.

    One generator per module: no table has a natural dedup key, and code length is a property of
    the module, not of an entity. A collision fails the insert rather than merging two rows.
    """
    return random_hash(CODE_LEN).upper()


def code_prefix(value: str) -> str:
    """The type word of an incoming code (``TASK`` from ``task@<hash>``); ``""`` — a bare code.

    A retired word comes back as its current one (``GROUP`` → ``TASKGROUP``): every check and
    dispatch by type goes through here, so an old code is accepted everywhere at once.
    """
    if "@" not in value:
        return ""
    word = value.split("@", 1)[0].upper()
    return LEGACY_CODE_PREFIXES.get(word, word)


def strip_prefix(value: str | None) -> str | None:
    """Boundary → storage: strip the presentation prefix, leaving the bare hash in upper case.

    Idempotent on a bare code (a hex hash has no ``@`` → only the case is folded).
    """
    return value.rpartition("@")[2].upper() if value else value


def bare_code(value: str | None, prefix: str) -> str | None:
    """The bare code of a ``prefix`` entity; a foreign prefix is refused, naming both types.

    A bare code passes without question: it is the internal form, and demanding a prefix on it
    would forbid passing back what the module itself returned.
    """
    if not value:
        return value
    actual = code_prefix(value)
    if actual and actual != prefix:
        raise ValueError(
            f"Code {value!r} is a {actual}@ reference, but a {prefix}@ code is expected here. "
            f"This is a wrong argument, not a missing row — pass the {prefix}@ code of the "
            "entity you mean (or its bare form)."
        )
    # An empty tail must not pass through: "empty" in CRUD means "clear" (move to the root,
    # remove from the group), and a truncated code would silently turn into that operation.
    hash_part = value.partition("@")[2] if actual else value
    if not hash_part or "@" in hash_part:
        raise ValueError(
            f"{value!r} is not a {prefix}@ code — expected {prefix}@ followed by the code "
            "itself, exactly as a tool returned it. To clear the field, pass an empty string."
        )
    return hash_part.upper()


def tagged(prefix: str, value: str | None) -> str | None:
    """Storage → boundary: a bare code's presentation form (``TASK@<hash>``); ``None`` → ``None``."""
    return value if value is None else f"{prefix}@{value}"


def prefixed(prefix: str):
    """A ``str`` type whose JSON form carries ``prefix@`` (input still accepts the bare hash).

    ``prefix`` is the bare type word (``TASK``/``TASKGROUP``/…); the ``@`` separator is appended
    here so the constant does not mix the type name with reference syntax. For the module's future
    DTOs.
    """
    return Annotated[
        str,
        PlainSerializer(
            lambda value: tagged(prefix, value), return_type=str, when_used="json"
        ),
    ]


__all__ = [
    "CODE_LEN",
    "bare_code",
    "code_prefix",
    "new_code",
    "prefixed",
    "strip_prefix",
    "tagged",
]
