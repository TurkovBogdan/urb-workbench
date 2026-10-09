"""ORM ``tasks_journal`` — the work journal: decisions, remarks, findings and facts in one table.

A row is a pair: the **subject** (``title`` + ``body``) and the **resolution** (``resolution``).
The subject says what was raised, the resolution says how it was closed. Hence the only state
there is here: an entry is open while ``resolution`` is empty (a ``fact`` is closed the moment it
is written), and the open entries are counted and reported when the task is handed in. There is no
separate column for that state — otherwise the agent would set it itself, bypassing the count.

``type`` decides what the row describes and who writes each half of it:

- ``decision`` — a choice made along the way; the agent writes the subject, the resolution comes
  from the person as a reply or from the agent itself as a pointer to the check. A decision with
  an empty resolution is an assumption; no separate kind is introduced for it;
- ``remark`` — a remark from the task's author; ONLY the person writes the subject (the agent has
  no tool with this type), the agent writes the resolution: how it was taken into account;
- ``finding`` — a discovery outside the task; the agent raises it, the person closes it;
- ``fact`` — something to remember going forward; closed the moment it is written and takes no
  part in the gate.

There is no ``created_by``: the author follows from the type. Entries are added, not rewritten —
the body alone takes detail later — so there is neither ``updated_at`` nor a closing timestamp:
a retraction is a new entry, and "when exactly it was closed" has no reader.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import CheckConstraint, ForeignKey, Index, String, text
from sqlalchemy.orm import Mapped, mapped_column

from src.core.database.runtime import Base
from src.core.database.types import timestamp
from src.core.utils.date import utc_now
from src.modules.tasks.constants import (
    CODE_LEN,
    ENUM_VALUE_MAX,
    JOURNAL_BODY_MAX,
    JOURNAL_TYPES,
    RESOLUTION_MAX,
    TITLE_MAX,
    sql_in,
)


class TasksJournal(Base):
    __tablename__ = "tasks_journal"
    __table_args__ = (
        CheckConstraint(f"type IN ({sql_in(JOURNAL_TYPES)})", name="ck_tasks_journal_type"),
        # The journal is read whole per task, in order of appearance — the index mirrors that
        # query and covers the child side of the ``task_code`` FK.
        Index("ix_tasks_journal_task_created", "task_code", "created_at"),
        Index("ix_tasks_journal_stage", "stage_code"),
    )

    code: Mapped[str] = mapped_column(String(CODE_LEN), primary_key=True)
    task_code: Mapped[str] = mapped_column(
        String(CODE_LEN),
        ForeignKey(
            "tasks.code", name="fk_tasks_journal_task_code", ondelete="CASCADE"
        ),
    )
    # An entry about work on a stage references it; an entry about the task as a whole — ``NULL``.
    # CASCADE, not SET NULL: a stage is only removed together with its task, so orphaned entries
    # never occur here.
    stage_code: Mapped[str | None] = mapped_column(
        String(CODE_LEN),
        ForeignKey(
            "tasks_stage.code", name="fk_tasks_journal_stage_code", ondelete="CASCADE"
        ),
        nullable=True,
    )
    type: Mapped[str] = mapped_column(String(ENUM_VALUE_MAX))
    title: Mapped[str] = mapped_column(String(TITLE_MAX))
    body: Mapped[str] = mapped_column(
        String(JOURNAL_BODY_MAX), default="", server_default=text("''")
    )
    resolution: Mapped[str] = mapped_column(
        String(RESOLUTION_MAX), default="", server_default=text("''")
    )
    created_at: Mapped[datetime] = mapped_column(timestamp(), default=utc_now)


__all__ = ["TasksJournal"]
