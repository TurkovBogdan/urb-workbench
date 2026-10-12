"""codex: codex_mount table

Creates ``codex_mount`` — a codex mounted into a workspace: PK (``codex_code``,
``workspace_code``), both FKs ``ON DELETE CASCADE``; ``sort`` orders the workspace's canvas and
``agent_can_edit`` (default true) says whether the agent may write notes of this codex there.

``depends_on`` points at ``wkm_001_workspaces``, which creates the FK target and is not the head
of its chain — a dependency on a head breaks the overlap check.

Revision ID: cxm_003_codex_mount
Revises: cxm_002_codex_note
Create Date: 2026-10-11
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from src.core.database.types import timestamp

revision: str = "cxm_003_codex_mount"
down_revision: Union[str, None] = "cxm_002_codex_note"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = "wkm_001_workspaces"

_TS = timestamp()


def upgrade() -> None:
    op.create_table(
        "codex_mount",
        sa.Column("codex_code", sa.String(length=10), primary_key=True, nullable=False),
        sa.Column("workspace_code", sa.String(length=10), primary_key=True, nullable=False),
        sa.Column("sort", sa.Integer(), nullable=False, server_default=sa.text("500")),
        sa.Column("agent_can_edit", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", _TS, nullable=False),
        sa.ForeignKeyConstraint(
            ["codex_code"], ["codex.code"], name="fk_codex_mount_codex_code", ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["workspace_code"],
            ["workspaces.code"],
            name="fk_codex_mount_workspace_code",
            ondelete="CASCADE",
        ),
    )
    op.create_index(
        "ix_codex_mount_workspace_sort", "codex_mount", ["workspace_code", "sort"]
    )


def downgrade() -> None:
    op.drop_index("ix_codex_mount_workspace_sort", table_name="codex_mount")
    op.drop_table("codex_mount")
