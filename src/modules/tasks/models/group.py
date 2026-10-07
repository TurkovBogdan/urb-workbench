"""ORM ``tasks_group`` — a group of tasks inside a workspace (billing, interface, infrastructure).

A group answers "which part of the work is this task about", not "what state is it in": it is a
standing layout of the subject area, not a board column. A task refers to its group through the
``tasks.group_code`` column (nullable → ``NULL`` = the task is in no group); there is no default
group.

The word is the same one the neighbouring module uses for its research layout
(``research_group``): the concept is one — a bucket of top-level entities with a title, a
description and styling — and a shared name spares the agent a second vocabulary. ``area`` was
rejected for exactly that reason: in research an area is part of a single study, not a bucket
over many.

``sort`` sets the order of groups in the interface: **higher sort = higher up**. A second sort
key is mandatory, otherwise groups with equal ``sort`` (and by default they all share one) swap
places between queries.

The FK to the workspace is ``CASCADE``: a group outside a workspace is meaningless, so hard
deleting the workspace takes it along. The usual deletion path is soft (``deleted_at``).
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import ForeignKey, Index, Integer, String, text
from sqlalchemy.orm import Mapped, mapped_column

from src.core.database import SoftDeleteMixin
from src.core.database.runtime import Base
from src.core.database.types import timestamp
from src.core.utils.date import utc_now
from src.modules.tasks.constants import (
    CODE_LEN,
    COLOR_MAX,
    GROUP_DESCRIPTION_MAX,
    ICON_MAX,
    SORT_DEFAULT,
    TITLE_MAX,
)


class TasksGroup(SoftDeleteMixin, Base):
    __tablename__ = "tasks_group"
    # An index on the child side of the FK: without it every workspace deletion reads the whole
    # groups table, and listing a workspace's groups is a full scan too.
    __table_args__ = (Index("ix_tasks_group_workspace_code", "workspace_code"),)

    code: Mapped[str] = mapped_column(String(CODE_LEN), primary_key=True)
    workspace_code: Mapped[str] = mapped_column(
        String(CODE_LEN),
        ForeignKey(
            "workspaces.code",
            name="fk_tasks_group_workspace_code",
            ondelete="CASCADE",
        ),
    )
    title: Mapped[str] = mapped_column(String(TITLE_MAX))
    description: Mapped[str] = mapped_column(
        String(GROUP_DESCRIPTION_MAX), default="", server_default=text("''")
    )
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


__all__ = ["TasksGroup"]
