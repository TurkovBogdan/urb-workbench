"""ORM ``codex_note`` — a record of a codex's tree: text, and children under it.

There is no folder/document flag: a note with children is a section, and its ``body`` is the
summary of what lies below — ``python/test`` holds the testing standard in brief, its children
``fixtures`` and ``factories`` the details. An empty ``body`` is a note that only groups.

The tree is an adjacency list: ``parent_code`` points at the parent note, ``NULL`` — the top level
of the codex. The path (``python/test/factories``) is not stored; it is assembled from the
segments on read, so moving a branch rewrites one row instead of every path below it.
``codex_code`` is kept on every row, not only on the top level: "every note of this codex" is one indexed query,
and the codex a code belongs to is known without climbing.

What the schema cannot hold is held by the service: the parent is in the same codex, there is no
cycle through several rows, the depth is at most four levels. The schema holds what it can: a note
is not its own parent, and a segment is unique among live siblings. That uniqueness needs two
partial indexes, because a plain ``UNIQUE (parent_code, segment)`` does not compare ``NULL`` with
``NULL`` on either provider — two top-level notes with one segment would both pass.

Deletion is soft by default (``deleted_at``), and a deleted note frees its segment. A hard delete
of a codex or a note takes the whole branch below through ``ON DELETE CASCADE``.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import CheckConstraint, ForeignKey, Index, Integer, String, text
from sqlalchemy.orm import Mapped, mapped_column

from src.core.database import SoftDeleteMixin
from src.core.database.runtime import Base
from src.core.database.types import timestamp
from src.core.utils.date import utc_now
from src.modules.codex.constants import (
    BODY_MAX,
    CODE_LEN,
    DESCRIPTION_MAX,
    SEGMENT_MAX,
    SORT_DEFAULT,
    TITLE_MAX,
)

_LIVE_CHILD = text("parent_code IS NOT NULL AND deleted_at IS NULL")
_LIVE_TOP = text("parent_code IS NULL AND deleted_at IS NULL")


class CodexNote(SoftDeleteMixin, Base):
    __tablename__ = "codex_note"
    __table_args__ = (
        CheckConstraint("code <> parent_code", name="ck_codex_note_not_own_parent"),
        Index(
            "ux_codex_note_parent_segment",
            "parent_code",
            "segment",
            unique=True,
            sqlite_where=_LIVE_CHILD,
            postgresql_where=_LIVE_CHILD,
        ),
        Index(
            "ux_codex_note_top_segment",
            "codex_code",
            "segment",
            unique=True,
            sqlite_where=_LIVE_TOP,
            postgresql_where=_LIVE_TOP,
        ),
        # A note's children in order; also the child side of the ``parent_code`` FK.
        Index("ix_codex_note_parent_sort", "parent_code", "sort"),
        # A codex's top level in order, and every note of a codex for the tree.
        Index("ix_codex_note_codex_sort", "codex_code", "parent_code", "sort"),
    )

    code: Mapped[str] = mapped_column(String(CODE_LEN), primary_key=True)
    codex_code: Mapped[str] = mapped_column(
        String(CODE_LEN),
        ForeignKey("codex.code", name="fk_codex_note_codex_code", ondelete="CASCADE"),
    )
    parent_code: Mapped[str | None] = mapped_column(
        String(CODE_LEN),
        ForeignKey("codex_note.code", name="fk_codex_note_parent_code", ondelete="CASCADE"),
        nullable=True,
    )
    segment: Mapped[str] = mapped_column(String(SEGMENT_MAX))
    title: Mapped[str] = mapped_column(String(TITLE_MAX))
    description: Mapped[str] = mapped_column(
        String(DESCRIPTION_MAX), default="", server_default=text("''")
    )
    body: Mapped[str] = mapped_column(String(BODY_MAX), default="", server_default=text("''"))
    sort: Mapped[int] = mapped_column(
        Integer, default=SORT_DEFAULT, server_default=text(str(SORT_DEFAULT))
    )
    created_at: Mapped[datetime] = mapped_column(timestamp(), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        timestamp(), default=utc_now, onupdate=utc_now
    )


__all__ = ["CodexNote"]
