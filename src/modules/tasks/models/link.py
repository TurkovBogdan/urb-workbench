"""ORM ``tasks_link`` — an edge of the task tree: where a task stands and under whom.

Exactly one row per task (``task_code`` is both the PK and the FK), so a task's "place in the
tree" is unique by construction, not by convention: a second parent physically does not fit
here. Without a link row the task does not belong to the tree at all — which is why
``task_create`` creates it in the same transaction as the task itself.

- ``parent_code`` ``NULL`` — the workspace root (not "the parent got lost"): a workspace has many
  roots, and they need no separate flag.
- ``sort`` — the position among siblings, **higher sort = higher up**; the ``SORT_STEP`` gap
  leaves room for inserts between siblings without renumbering the list.

A parent's children form a single run: there are no sub-heading buckets inside the link, and
``sort`` carries the whole order.

There is no ``created_at`` here on purpose: the edge appears when the task does, and duplicating
that time would create a second source of truth. ``updated_at`` is here — it answers a different
question: when the branch was last moved.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import ForeignKey, Index, Integer, String, text
from sqlalchemy.orm import Mapped, mapped_column

from src.core.database.runtime import Base
from src.core.database.types import timestamp
from src.core.utils.date import utc_now
from src.modules.tasks.constants import CODE_LEN, SORT_DEFAULT


class TasksLink(Base):
    __tablename__ = "tasks_link"
    # The tree's main query is "the children of X, in order"; the index returns them already
    # sorted and also covers the child side of the ``parent_code`` FK.
    __table_args__ = (Index("ix_tasks_link_parent_sort", "parent_code", "sort"),)

    task_code: Mapped[str] = mapped_column(
        String(CODE_LEN),
        ForeignKey(
            "tasks.code", name="fk_tasks_link_task_code", ondelete="CASCADE"
        ),
        primary_key=True,
    )
    parent_code: Mapped[str | None] = mapped_column(
        String(CODE_LEN),
        ForeignKey(
            "tasks.code", name="fk_tasks_link_parent_code", ondelete="CASCADE"
        ),
        nullable=True,
    )
    sort: Mapped[int] = mapped_column(
        Integer, default=SORT_DEFAULT, server_default=text(str(SORT_DEFAULT))
    )
    updated_at: Mapped[datetime] = mapped_column(
        timestamp(), default=utc_now, onupdate=utc_now
    )


__all__ = ["TasksLink"]
