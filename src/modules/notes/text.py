"""The length limit of a note's fields: refused with the numbers, never cut.

Counted by **code points** — ``len`` on a ``str`` counts Unicode characters, not bytes, which
matches ``VARCHAR(n)`` on PostgreSQL. SQLite does not check width at all, so here the CRUD is the
only limit.
"""

from __future__ import annotations


def fit(value: str | None, limit: int, field: str) -> str:
    """The whole string, or a ``ValueError`` stating the overrun; ``None`` → ``""``.

    The message names the limit and the actual length: "shorten it" without a number leaves the
    caller guessing by how much.
    """
    text = value or ""
    if len(text) > limit:
        raise ValueError(
            f"{field} is {len(text)} characters long, the limit is {limit} — "
            f"shorten it by {len(text) - limit} and send again."
        )
    return text


__all__ = ["fit"]
