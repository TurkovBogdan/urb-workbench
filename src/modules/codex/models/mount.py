"""ORM ``codex_mount`` — a codex mounted into a workspace, and what the agent may do with it there.

Only the person mounts and unmounts; the agent sees the mounted codexes of its workspace as one
canvas and nothing else. There is no codex "for every workspace" — only an explicit mount.

``agent_can_edit`` belongs to the mount, not to the codex: one codex may be open for writing in
the project that maintains it and read-only in the projects that follow it. It defaults to
``true`` — a person who mounts a codex is assumed to want the agent to keep it current.

A mount is a link, not a record with a history: unmounting deletes the row, and so does a hard
delete of either side.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, ForeignKey, Index, Integer, String, text, true
from sqlalchemy.orm import Mapped, mapped_column

from src.core.database.runtime import Base
from src.core.database.types import timestamp
from src.core.utils.date import utc_now
from src.modules.codex.constants import CODE_LEN, SORT_DEFAULT
from src.modules.workspace import models as workspace_models  # noqa: F401 — the FK target in the metadata


class CodexMount(Base):
    __tablename__ = "codex_mount"
    # The canvas of a workspace in order; also the child side of the ``workspace_code`` FK.
    __table_args__ = (Index("ix_codex_mount_workspace_sort", "workspace_code", "sort"),)

    codex_code: Mapped[str] = mapped_column(
        String(CODE_LEN),
        ForeignKey("codex.code", name="fk_codex_mount_codex_code", ondelete="CASCADE"),
        primary_key=True,
    )
    workspace_code: Mapped[str] = mapped_column(
        String(CODE_LEN),
        ForeignKey("workspaces.code", name="fk_codex_mount_workspace_code", ondelete="CASCADE"),
        primary_key=True,
    )
    sort: Mapped[int] = mapped_column(
        Integer, default=SORT_DEFAULT, server_default=text(str(SORT_DEFAULT))
    )
    agent_can_edit: Mapped[bool] = mapped_column(Boolean, default=True, server_default=true())
    created_at: Mapped[datetime] = mapped_column(timestamp(), default=utc_now)


__all__ = ["CodexMount"]
