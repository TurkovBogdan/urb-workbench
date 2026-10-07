"""ORM ``tasks_stage`` — a plan stage: a unit of work inside a task.

Stages exist on tasks of type ``standard`` and heavier: ``simple`` is a card without a plan. The
plan itself, as prose, lives in ``tasks.body``; here are the concrete steps, each with its own
state and evidence.

Order is kept by ``number``, not by the ``sort`` of the neighbouring tables: a stage's number is
part of its name in conversation ("third attempt at stage two"), and it grows downwards, from
first to last. The ``(task_code, number)`` pair is unique — without that, two stages numbered 3
would appear on day one and the order would become undefined. To insert in the middle, pass the
number explicitly and shift the tail.

``status`` uses the same vocabulary as the task and differs only in its default: a stage is
created already scheduled (``planned``), because it is part of the plan, not an idea for later.

``evidence`` is a pointer to proof of completion: a command and its result, a path to a changed
file, a diff summary. A transition to ``done`` with empty ``evidence`` is refused on write
(``crud``): otherwise a step would be marked done without a check, the following steps would
reason from a false premise, and the task would end "successfully". The system sets
``finished_at`` on entering a terminal status.

A stage has no soft delete: a plan never lacks its stages, and a chosen-then-abandoned stage is
``canceled``, not a hidden row.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import CheckConstraint, ForeignKey, Index, Integer, String, text
from sqlalchemy.orm import Mapped, mapped_column

from src.core.database.runtime import Base
from src.core.database.types import timestamp
from src.core.utils.date import utc_now
from src.modules.tasks.constants import (
    BODY_MAX,
    CODE_LEN,
    DESCRIPTION_MAX,
    ENUM_VALUE_MAX,
    EVIDENCE_MAX,
    STAGE_STATUS_DEFAULT,
    TASK_STATUSES,
    TITLE_MAX,
    sql_in,
)


class TasksStage(Base):
    __tablename__ = "tasks_stage"
    __table_args__ = (
        CheckConstraint(
            f"status IN ({sql_in(TASK_STATUSES)})", name="ck_tasks_stage_status"
        ),
        # Uniqueness and order in one index: it also returns a task's stages already sorted and
        # covers the child side of the ``task_code`` FK.
        Index("ix_tasks_stage_task_number", "task_code", "number", unique=True),
    )

    code: Mapped[str] = mapped_column(String(CODE_LEN), primary_key=True)
    task_code: Mapped[str] = mapped_column(
        String(CODE_LEN),
        ForeignKey(
            "tasks.code", name="fk_tasks_stage_task_code", ondelete="CASCADE"
        ),
    )
    number: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(
        String(ENUM_VALUE_MAX),
        default=STAGE_STATUS_DEFAULT,
        server_default=text(f"'{STAGE_STATUS_DEFAULT}'"),
    )
    title: Mapped[str] = mapped_column(String(TITLE_MAX))
    description: Mapped[str] = mapped_column(
        String(DESCRIPTION_MAX), default="", server_default=text("''")
    )
    body: Mapped[str] = mapped_column(
        String(BODY_MAX), default="", server_default=text("''")
    )
    evidence: Mapped[str] = mapped_column(
        String(EVIDENCE_MAX), default="", server_default=text("''")
    )
    started_at: Mapped[datetime | None] = mapped_column(timestamp(), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(timestamp(), nullable=True)
    created_at: Mapped[datetime] = mapped_column(timestamp(), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        timestamp(), default=utc_now, onupdate=utc_now
    )


__all__ = ["TasksStage"]
