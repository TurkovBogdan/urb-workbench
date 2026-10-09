"""ORM ``notes`` — a document: a title, what it is about, and the markdown text itself.

A note knows nothing of where it is used. A task's planning documents, a project's documentation
and a knowledge base all hold notes, and each of them keeps the link in a table of its own: which
note belongs to which task, where a note stands in a tree. Hence no owner, workspace, parent or
position here — those are properties of a use, not of the document, and one document may move
from a task to the project's documentation keeping its code and every reference to it.

The class is ``Note`` and the table ``notes``, without the module-name prefix: there is one entity
and it coincides with the module, as with ``workspaces``.

The PK is a bare hex code of length ``CODE_LEN``; ``NOTE@`` lives at the boundary
(``notes.codes``). Deletion is logical by default (``deleted_at``); a hard delete takes the
consumers' links along through their own ``ON DELETE CASCADE``.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Index, String, text
from sqlalchemy.orm import Mapped, mapped_column

from src.core.database import SoftDeleteMixin
from src.core.database.runtime import Base
from src.core.database.types import timestamp
from src.core.utils.date import utc_now
from src.modules.notes.constants import BODY_MAX, CODE_LEN, DESCRIPTION_MAX, TITLE_MAX


class Note(SoftDeleteMixin, Base):
    __tablename__ = "notes"
    # The list of every document: live ones, newest change first.
    __table_args__ = (Index("ix_notes_deleted_updated", "deleted_at", "updated_at"),)

    code: Mapped[str] = mapped_column(String(CODE_LEN), primary_key=True)
    title: Mapped[str] = mapped_column(String(TITLE_MAX))
    description: Mapped[str] = mapped_column(
        String(DESCRIPTION_MAX), default="", server_default=text("''")
    )
    body: Mapped[str] = mapped_column(String(BODY_MAX), default="", server_default=text("''"))
    created_at: Mapped[datetime] = mapped_column(timestamp(), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        timestamp(), default=utc_now, onupdate=utc_now
    )


__all__ = ["Note"]
