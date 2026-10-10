"""Reading an incoming code by its type word — what the shared tools dispatch on.

``delete``, ``interface_open`` and ``content_*`` take a code of any type and pick the handler by
its prefix. The type word is read here, for every module at once: a domain module's own
``code_prefix`` knows its own words, and dispatch across modules cannot rest on one of them.

A retired type word is read as its current one (``GROUP@`` → ``TASKGROUP@``), so codes quoted
before a rename keep resolving on every shared tool. The retired words are the owning module's
fact (``tasks.constants.LEGACY_CODE_PREFIXES``) and are taken from there.

A tool argument of ONE known type (``task_code``, ``group_code``) is parsed by the module that
owns the type (``tasks.codes.bare_code`` / ``workspace.codes.bare_code``): the person's HTTP API
parses the same codes with the same refusals, and the two must not drift. ``bare_code`` here is
for a code whose type was just read off it, whatever module it belongs to.
"""

from __future__ import annotations

from src.modules.tasks.constants import LEGACY_CODE_PREFIXES

# Retired type word → the current one, across every module below.
_LEGACY_PREFIXES: dict[str, str] = {**LEGACY_CODE_PREFIXES}


def code_prefix(value: str) -> str:
    """The current type word of an incoming code (``TASK`` from ``task@<hash>``); ``""`` — bare."""
    if "@" not in value:
        return ""
    word = value.split("@", 1)[0].upper()
    return _LEGACY_PREFIXES.get(word, word)


def strip_prefix(value: str | None) -> str | None:
    """The bare hash of a code, upper case; idempotent on a bare code."""
    return value.rpartition("@")[2].upper() if value else value


def bare_code(value: str | None, prefix: str) -> str | None:
    """The bare code of a ``prefix`` entity; a foreign type or a truncated code is refused.

    The same contract as a domain module's ``bare_code``, over every module's type words — so a
    shared tool, having picked the handler by the prefix, refuses a ``TASK@`` with nothing after
    it in the same words a typed argument would.
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
    # An empty tail must not pass through: an empty code downstream means "none", and a
    # truncated code would silently turn into that.
    hash_part = value.partition("@")[2] if actual else value
    if not hash_part or "@" in hash_part:
        raise ValueError(
            f"{value!r} is not a {prefix}@ code — expected {prefix}@ followed by the code "
            "itself, exactly as a tool returned it. To clear the field, pass an empty string."
        )
    return hash_part.upper()


def tagged(prefix: str, value: str | None) -> str | None:
    """A bare code's presentation form (``TASK@<hash>``); ``None`` → ``None``."""
    return value if value is None else f"{prefix}@{value}"


__all__ = ["bare_code", "code_prefix", "strip_prefix", "tagged"]
