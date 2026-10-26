"""ORM ``codex_file`` — a file of ``core_storage`` bound to a codex note.

The bytes, the type and the name the file came under are the storage's; here is what the file is
to the note: its title there, what is inside it, its place in the note's list. A file is in a note
once — ``(note_code, file_code)`` is the PK.

The holder is a note, never the codex itself: the two share the ``CODEX@`` prefix, and the FK on
``codex_note`` is what keeps a codex code out. Every row has exactly one live owner row in the
storage, ``("CODEX", note_code, "")``. The cascades are a safety net — they take a row with its
note or file, but cannot release the owner; the codex has no final deletion a person or the agent
can reach, and its CRUD's hard paths release the owners themselves.

``sort`` orders a note's files, **higher sort = higher up**: a new file goes to the end, the person
reorders by hand.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import ForeignKey, Index, Integer, String, text
from sqlalchemy.orm import Mapped, mapped_column

from src.core.database.runtime import Base
from src.core.database.types import timestamp
from src.core.utils.date import utc_now
from src.modules.codex.constants import CODE_LEN, FILE_DESCRIPTION_MAX, FILE_TITLE_MAX, SORT_DEFAULT
from src.modules.core_storage import models as storage_models  # noqa: F401 — the FK target in the metadata


class CodexFile(Base):
    __tablename__ = "codex_file"
    # Where a file is bound — and the child side of the ``file_code`` FK; the ``note_code`` side is
    # the PK's leading column.
    __table_args__ = (Index("ix_codex_file_file_code", "file_code"),)

    note_code: Mapped[str] = mapped_column(
        String(CODE_LEN),
        ForeignKey("codex_note.code", name="fk_codex_file_note_code", ondelete="CASCADE"),
        primary_key=True,
    )
    file_code: Mapped[str] = mapped_column(
        String(CODE_LEN),
        ForeignKey("core_storage_file.code", name="fk_codex_file_file_code", ondelete="CASCADE"),
        primary_key=True,
    )
    title: Mapped[str] = mapped_column(
        String(FILE_TITLE_MAX), default="", server_default=text("''")
    )
    description: Mapped[str] = mapped_column(
        String(FILE_DESCRIPTION_MAX), default="", server_default=text("''")
    )
    sort: Mapped[int] = mapped_column(
        Integer, default=SORT_DEFAULT, server_default=text(str(SORT_DEFAULT))
    )
    created_at: Mapped[datetime] = mapped_column(timestamp(), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        timestamp(), default=utc_now, onupdate=utc_now
    )


__all__ = ["CodexFile"]
