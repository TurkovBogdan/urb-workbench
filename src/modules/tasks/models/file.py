"""ORM ``tasks_file`` — a file of ``core_storage`` bound to a task.

The bytes, the type and the name the file came under are the storage's; here is what the file is
to the task: its title there, what is inside it, its place in the list. A file is in a task once —
``(task_code, file_code)`` is the PK — and ``note_code`` / ``stage_code`` say where in the task it
was attached, not a second place: the agent attaches a screenshot to a stage and refers to it in
the whole task afterwards. At most one of the two is set; neither — the task as a whole. That the
note or the stage is this task's is the service's check: the FKs only say they exist.

Every row has exactly one live owner row in the storage, ``("TASK", task_code, "")``: the task
holds the file, its notes and stages are not seen there. The cascades are a safety net — they take
a row with its holder, but cannot release the storage owner; the deletion functions in ``crud``
take the rows themselves and release the owners after the commit.

``sort`` orders a task's files, **higher sort = higher up**, with the module's step: a new file
goes to the end, the person reorders by hand.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import CheckConstraint, ForeignKey, Index, Integer, String, text
from sqlalchemy.orm import Mapped, mapped_column

from src.core.database.runtime import Base
from src.core.database.types import timestamp
from src.core.utils.date import utc_now
from src.modules.core_storage import models as storage_models  # noqa: F401 — the FK target in the metadata
from src.modules.notes import models as notes_models  # noqa: F401 — the FK target in the metadata
from src.modules.tasks.constants import (
    CODE_LEN,
    FILE_DESCRIPTION_MAX,
    FILE_TITLE_MAX,
    SORT_DEFAULT,
)


class TasksFile(Base):
    __tablename__ = "tasks_file"
    __table_args__ = (
        CheckConstraint(
            "note_code IS NULL OR stage_code IS NULL", name="ck_tasks_file_one_place"
        ),
        # Where a file is bound — and the child side of the ``file_code`` FK.
        Index("ix_tasks_file_file_code", "file_code"),
        Index("ix_tasks_file_note_code", "note_code"),
        Index("ix_tasks_file_stage_code", "stage_code"),
    )

    task_code: Mapped[str] = mapped_column(
        String(CODE_LEN),
        ForeignKey("tasks.code", name="fk_tasks_file_task_code", ondelete="CASCADE"),
        primary_key=True,
    )
    file_code: Mapped[str] = mapped_column(
        String(CODE_LEN),
        ForeignKey("core_storage_file.code", name="fk_tasks_file_file_code", ondelete="CASCADE"),
        primary_key=True,
    )
    note_code: Mapped[str | None] = mapped_column(
        String(CODE_LEN),
        ForeignKey("notes.code", name="fk_tasks_file_note_code", ondelete="CASCADE"),
        nullable=True,
    )
    stage_code: Mapped[str | None] = mapped_column(
        String(CODE_LEN),
        ForeignKey("tasks_stage.code", name="fk_tasks_file_stage_code", ondelete="CASCADE"),
        nullable=True,
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


__all__ = ["TasksFile"]
