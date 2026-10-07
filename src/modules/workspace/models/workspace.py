"""ORM ``workspaces`` — a workspace, the top level of data isolation.

A workspace belongs to no application module: it answers the question "what am I working in
right now", and the modules above (tasks today, documentation tomorrow) keep a reference to it to
narrow their queries. The separate level exists not for access control (there is one user) but
so that "work" and, say, "personal" do not mix in one list.

The class is named ``Workspace``, without the module-name prefix (``TasksGroup`` and its
neighbours carry one): there is a single entity here and it coincides with the module, so
``WorkspaceWorkspace`` would be repetition for the sake of a naming scheme, not for clarity. The
TABLE name is ``workspaces``, also unprefixed for the same reason: the prefix answers "whose is
this" in modules with several entities (``tasks_group``, ``tasks_task``), whereas here the name
itself answers it, and ``workspace_workspace`` would be the same stutter at the schema level.

The card is minimal: ``title``/``description`` (what it is), ``icon``/``color`` — styling
(``''`` = not chosen, the frontend draws a fallback). Neither icon nor colour is validated in
the DB: only the frontend knows how to draw them, and a check on write would turn extending a
palette into editing two files in two languages.

``sort`` sets the order of workspaces in the list and the switcher, the same way as a task
group's: **higher sort = higher up**, then by title, then by code — without the second and third
keys rows with equal ``sort`` (by default they all share one) would swap places between queries.

The PK is a bare hex code of length ``CODE_LEN``; the ``WORKSPACE@`` type prefix lives at the
boundary (``workspace.codes``) and is not in the database. Deletion is logical (``deleted_at``).
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Index, Integer, String, text
from sqlalchemy.orm import Mapped, mapped_column

from src.core.database import SoftDeleteMixin
from src.core.database.runtime import Base
from src.core.database.types import timestamp
from src.core.utils.date import utc_now
from src.modules.workspace.constants import (
    CODE_LEN,
    COLOR_MAX,
    DESCRIPTION_MAX,
    ICON_MAX,
    SORT_DEFAULT,
    TITLE_MAX,
)


class Workspace(SoftDeleteMixin, Base):
    __tablename__ = "workspaces"

    # The module's only query is the list: filter out deleted rows, then order by position, title
    # and code as the last tiebreaker. The index mirrors it, hence the column order.
    __table_args__ = (
        Index("ix_workspaces_deleted_sort", "deleted_at", "sort", "title", "code"),
    )

    code: Mapped[str] = mapped_column(String(CODE_LEN), primary_key=True)
    title: Mapped[str] = mapped_column(String(TITLE_MAX))
    description: Mapped[str] = mapped_column(
        String(DESCRIPTION_MAX), default="", server_default=text("''")
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


__all__ = ["Workspace"]
