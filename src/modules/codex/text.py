"""The length limit of a codex's fields: refused with the numbers, never cut.

Counted by code points, which matches ``VARCHAR(n)`` on PostgreSQL; SQLite does not check width at
all, so the service is the only limit there.
"""

from __future__ import annotations


def fit(value: str | None, limit: int, field: str) -> str:
    """The whole string, or a ``ValueError`` stating the overrun; ``None`` → ``""``."""
    text = value or ""
    if len(text) > limit:
        raise ValueError(
            f"{field} is {len(text)} characters long, the limit is {limit} — "
            f"shorten it by {len(text) - limit} and send again."
        )
    return text


__all__ = ["fit"]
