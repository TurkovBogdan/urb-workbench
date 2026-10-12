"""ORM ``codex`` — a codex: a set of development rules on one theme, not tied to any project.

A codex is the root of its tree of notes (``codex_note``) and carries the rules of working in it
(``body``) — what ``codex_get`` hands the agent as the codex's root. ``description`` is "when to turn to it": the
line by which the agent decides from the index whether this codex is needed at all.

``segment`` is the first segment of every path inside the codex (``python`` in ``python/test``).
It is unique among live codexes: two codexes with one segment could not be mounted into one
workspace, and a segment that is free in one workspace but taken in another would make mounting
fail far from the place the name was chosen. A soft-deleted codex frees its segment — hence the
partial index.

``icon``/``color`` are the codex's look, as a workspace's and a task group's: names from the
frontend's palettes, ``''`` — not chosen. Only the root has them, and only the person sets them.

Only the person edits a codex; the agent writes notes inside it.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Index, Integer, String, text
from sqlalchemy.orm import Mapped, mapped_column

from src.core.database import SoftDeleteMixin
from src.core.database.runtime import Base
from src.core.database.types import timestamp
from src.core.utils.date import utc_now
from src.modules.codex.constants import (
    BODY_MAX,
    CODE_LEN,
    COLOR_MAX,
    DESCRIPTION_MAX,
    ICON_MAX,
    SEGMENT_MAX,
    SORT_DEFAULT,
    TITLE_MAX,
)

_LIVE = text("deleted_at IS NULL")


class Codex(SoftDeleteMixin, Base):
    __tablename__ = "codex"
    __table_args__ = (
        Index(
            "ux_codex_segment", "segment", unique=True, sqlite_where=_LIVE, postgresql_where=_LIVE
        ),
    )

    code: Mapped[str] = mapped_column(String(CODE_LEN), primary_key=True)
    segment: Mapped[str] = mapped_column(String(SEGMENT_MAX))
    title: Mapped[str] = mapped_column(String(TITLE_MAX))
    description: Mapped[str] = mapped_column(
        String(DESCRIPTION_MAX), default="", server_default=text("''")
    )
    body: Mapped[str] = mapped_column(String(BODY_MAX), default="", server_default=text("''"))
    color: Mapped[str] = mapped_column(
        String(COLOR_MAX), default="", server_default=text("''")
    )
    icon: Mapped[str] = mapped_column(
        String(ICON_MAX), default="", server_default=text("''")
    )
    sort: Mapped[int] = mapped_column(
        Integer, default=SORT_DEFAULT, server_default=text(str(SORT_DEFAULT))
    )
    created_at: Mapped[datetime] = mapped_column(timestamp(), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        timestamp(), default=utc_now, onupdate=utc_now
    )


__all__ = ["Codex"]
