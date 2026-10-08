"""ORM ``tasks`` — the task itself: a unit of work for the person or the executing agent.

The table is named after the module, without a prefix: the task is its main entity, and
``tasks_task`` would be a stutter. The satellites carry the prefix (``tasks_group``,
``tasks_link``, ``tasks_stage``, ``tasks_note``) — there it answers "whose is this".

A row describes the whole task **except its place in the tree**: the parent and the position
among siblings live in ``tasks_link``. The reason: moving a branch or reordering siblings touches
only the link table, and the task card (its text, dates, status) is not rewritten; the same
decoupling allows changing the shape of the tree without touching the main table.

The vocabulary fields — ``type`` (depth of tracking), ``status`` (where it is in the work),
``priority`` (how urgent), ``created_by`` (who created it) — are stored as strings with named
``CHECK``s, not a native enum: ``CREATE TYPE`` does not exist on SQLite, and the module's
migrations run on both providers.

The text is split by owner. The person writes the brief: ``description`` is the goal,
``context`` the details and starting requirements, ``constraints`` what is and is not allowed,
``criteria`` the acceptance requirements. The agent writes the work: ``plan`` before the code
changes, ``progress`` along the way, ``result`` at hand-over. That is why a task has no ``body``
like the module's other entities: its text is several fields, and ``body`` would not say which.
The work fields close the text block in the order the work goes.

Dates are split by meaning:

- ``deadline_at`` — the deadline, a ``timestamp``: the only date a task is assigned;
- ``started_at`` / ``completed_at`` / ``canceled_at`` — phase marks, set on status change
  (``crud/task.py::task_update_status``): they are facts, not plans. The start is never
  overwritten; the two closing marks are cleared when the task is reopened and stamped anew when
  it closes again.

The indexes serve the three queries all output consists of: the workspace board by status, the
layout by group, and the schedule by deadline. All three lead with ``workspace_code`` — the
module never reads across workspaces.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import CheckConstraint, ForeignKey, Index, String, text
from sqlalchemy.orm import Mapped, mapped_column

from src.core.database import SoftDeleteMixin
from src.core.database.runtime import Base
from src.core.database.types import timestamp
from src.core.utils.date import utc_now
from src.modules.tasks.constants import (
    ACTOR_KINDS,
    CODE_LEN,
    CONSTRAINTS_MAX,
    CONTEXT_MAX,
    CRITERIA_MAX,
    DESCRIPTION_MAX,
    ENUM_VALUE_MAX,
    PLAN_MAX,
    PROGRESS_MAX,
    RESULT_MAX,
    TASK_CREATED_BY_DEFAULT,
    TASK_PRIORITIES,
    TASK_PRIORITY_DEFAULT,
    TASK_STATUS_DEFAULT,
    TASK_STATUSES,
    TASK_TYPE_DEFAULT,
    TASK_TYPES,
    TITLE_MAX,
    sql_in,
)


class TasksTask(SoftDeleteMixin, Base):
    __tablename__ = "tasks"
    __table_args__ = (
        CheckConstraint(f"type IN ({sql_in(TASK_TYPES)})", name="ck_tasks_type"),
        CheckConstraint(f"status IN ({sql_in(TASK_STATUSES)})", name="ck_tasks_status"),
        CheckConstraint(
            f"priority IN ({sql_in(TASK_PRIORITIES)})", name="ck_tasks_priority"
        ),
        CheckConstraint(
            f"created_by IN ({sql_in(ACTOR_KINDS)})", name="ck_tasks_created_by"
        ),
        Index("ix_tasks_workspace_status", "workspace_code", "status"),
        Index("ix_tasks_workspace_group", "workspace_code", "group_code"),
        Index("ix_tasks_workspace_deadline", "workspace_code", "deadline_at"),
    )

    code: Mapped[str] = mapped_column(String(CODE_LEN), primary_key=True)
    workspace_code: Mapped[str] = mapped_column(
        String(CODE_LEN),
        ForeignKey(
            "workspaces.code",
            name="fk_tasks_workspace_code",
            ondelete="CASCADE",
        ),
    )
    # SET NULL, not CASCADE: a group is deleted when the layout changes — its tasks remain work,
    # they just stop being sorted into a group.
    group_code: Mapped[str | None] = mapped_column(
        String(CODE_LEN),
        ForeignKey(
            "tasks_group.code", name="fk_tasks_group_code", ondelete="SET NULL"
        ),
        nullable=True,
    )
    type: Mapped[str] = mapped_column(
        String(ENUM_VALUE_MAX),
        default=TASK_TYPE_DEFAULT,
        server_default=text(f"'{TASK_TYPE_DEFAULT}'"),
    )
    status: Mapped[str] = mapped_column(
        String(ENUM_VALUE_MAX),
        default=TASK_STATUS_DEFAULT,
        server_default=text(f"'{TASK_STATUS_DEFAULT}'"),
    )
    priority: Mapped[str] = mapped_column(
        String(ENUM_VALUE_MAX),
        default=TASK_PRIORITY_DEFAULT,
        server_default=text(f"'{TASK_PRIORITY_DEFAULT}'"),
    )
    title: Mapped[str] = mapped_column(String(TITLE_MAX))
    description: Mapped[str] = mapped_column(
        String(DESCRIPTION_MAX), default="", server_default=text("''")
    )
    context: Mapped[str] = mapped_column(
        String(CONTEXT_MAX), default="", server_default=text("''")
    )
    constraints: Mapped[str] = mapped_column(
        String(CONSTRAINTS_MAX), default="", server_default=text("''")
    )
    criteria: Mapped[str] = mapped_column(
        String(CRITERIA_MAX), default="", server_default=text("''")
    )
    plan: Mapped[str] = mapped_column(
        String(PLAN_MAX), default="", server_default=text("''")
    )
    progress: Mapped[str] = mapped_column(
        String(PROGRESS_MAX), default="", server_default=text("''")
    )
    result: Mapped[str] = mapped_column(
        String(RESULT_MAX), default="", server_default=text("''")
    )
    deadline_at: Mapped[datetime | None] = mapped_column(timestamp(), nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(timestamp(), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(timestamp(), nullable=True)
    canceled_at: Mapped[datetime | None] = mapped_column(timestamp(), nullable=True)
    created_by: Mapped[str] = mapped_column(
        String(ENUM_VALUE_MAX),
        default=TASK_CREATED_BY_DEFAULT,
        server_default=text(f"'{TASK_CREATED_BY_DEFAULT}'"),
    )
    created_at: Mapped[datetime] = mapped_column(timestamp(), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        timestamp(), default=utc_now, onupdate=utc_now
    )


__all__ = ["TasksTask"]
