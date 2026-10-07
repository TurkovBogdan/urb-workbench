"""Length limits for the module's text fields: soft for a card, hard for a plan.

An oversized card field is **not** a validation error: a title that is too long is no reason to
refuse writing the task. So ``clip`` truncates instead of raising, and it does so in CRUD, on the
way into storage.

We cut by **code points**: ``value[:limit]`` on a ``str`` counts Unicode characters, not bytes, so
Cyrillic is never split mid-character. This matches the character semantics of ``VARCHAR(n)`` in
PostgreSQL; SQLite does not check the width at all, so there truncation is the only real limit.

**The exception is the task plan (``tasks_task.body``).** There ``fit`` refuses instead of
truncating, and not for tidiness: a plan must name the files it read and the files it touches,
and the agent writes that list at the end. Silent truncation would cut exactly that list — the
one part the plan is kept for. The refusal states the overrun, and the agent shortens the text
itself, with judgement.

The functions are shared across the module (not private to each CRUD file): the rule is one for
every table, and its copies have no reason to drift apart.
"""

from __future__ import annotations


def clip(value: str | None, limit: int) -> str:
    """Truncate to ``limit`` Unicode characters; ``None`` → ``""`` (the column is not nullable)."""
    return (value or "")[:limit]


def fit(value: str | None, limit: int, field: str) -> str:
    """The whole string, or a ``ValueError`` stating the overrun; ``None`` → ``""``.

    The message names both the limit and the actual length: "shorten it" without a number leaves
    the agent guessing by how much.
    """
    text = value or ""
    if len(text) > limit:
        raise ValueError(
            f"{field} is {len(text)} characters long, the limit is {limit} — "
            f"shorten it by {len(text) - limit} and send again."
        )
    return text


__all__ = ["clip", "fit"]
