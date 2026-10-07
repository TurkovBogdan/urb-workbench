"""Length limits for the module's text fields: soft for most, hard for the description.

Field size is mostly **not** a validation error: a title that is too long is no reason to refuse
the write. Hence ``clip`` — truncation rather than an exception, in the CRUD, at the entrance to
the store.

**The exception is the description.** It is one short line, and its end is where the point of it
usually sits, so ``fit`` refuses with the numbers instead of cutting — the same rule as a task
group's description in ``tasks``.

We count by **code points**: ``len``/``value[:limit]`` on a ``str`` count Unicode characters, not
bytes, so Cyrillic is never chopped mid-character. This matches the character semantics of
``VARCHAR(n)`` in PostgreSQL; SQLite does not check width at all — there the CRUD is the only
limit.
"""

from __future__ import annotations


def clip(value: str | None, limit: int) -> str:
    """Truncate a string to ``limit`` Unicode characters; ``None`` → ``""`` (column not nullable)."""
    return (value or "")[:limit]


def fit(value: str | None, limit: int, field: str) -> str:
    """The whole string, or a ``ValueError`` stating the overrun; ``None`` → ``""``.

    The message names both the limit and the actual length: "shorten it" without a number leaves
    the caller guessing by how much.
    """
    text = value or ""
    if len(text) > limit:
        raise ValueError(
            f"{field} is {len(text)} characters long, the limit is {limit} — "
            f"shorten it by {len(text) - limit} and send again."
        )
    return text


__all__ = ["clip", "fit"]
