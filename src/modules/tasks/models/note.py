"""ORM ``tasks_note`` — a task note: which task a document of the ``notes`` module belongs to.

The document itself — title, description, text — lives in ``notes``, which knows nothing of
tasks. This row is the task's half: a note is created together with its task's row here and
belongs to that one task, so ``note_code`` is both the PK and the FK, as ``task_code`` is in
``tasks_link`` — a second owner physically does not fit.

``sort`` orders a task's notes, **higher sort = higher up**, with the module's step. Deleting the
task hard takes these rows with it; the documents stay in ``notes``, owned by nobody.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import ForeignKey, Index, Integer, String, text
from sqlalchemy.orm import Mapped, mapped_column

from src.core.database.runtime import Base
from src.core.database.types import timestamp
from src.core.utils.date import utc_now
from src.modules.notes import models as notes_models  # noqa: F401 — the FK target in the metadata
from src.modules.tasks.constants import CODE_LEN, SORT_DEFAULT


class TasksNote(Base):
    __tablename__ = "tasks_note"
    # A task's notes in order; also the child side of the ``task_code`` FK.
    __table_args__ = (Index("ix_tasks_note_task_sort", "task_code", "sort"),)

    note_code: Mapped[str] = mapped_column(
        String(CODE_LEN),
        ForeignKey("notes.code", name="fk_tasks_note_note_code", ondelete="CASCADE"),
        primary_key=True,
    )
    task_code: Mapped[str] = mapped_column(
        String(CODE_LEN),
        ForeignKey("tasks.code", name="fk_tasks_note_task_code", ondelete="CASCADE"),
    )
    sort: Mapped[int] = mapped_column(
        Integer, default=SORT_DEFAULT, server_default=text(str(SORT_DEFAULT))
    )
    created_at: Mapped[datetime] = mapped_column(timestamp(), default=utc_now)


__all__ = ["TasksNote"]
