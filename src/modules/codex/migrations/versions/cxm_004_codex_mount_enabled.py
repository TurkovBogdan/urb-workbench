"""codex: codex_mount.enabled — switching a codex off keeps its place in the workspace's order

Until now unmounting deleted the row, and with it the codex's position among the workspace's
codexes: switching it back on put it at the end. ``enabled`` (default true — every existing row is
a live mount) lets the row stay when the codex is switched off, so the order the person arranged
holds for the codexes in use and the ones set aside alike.

Revision ID: cxm_004_codex_mount_enabled
Revises: cxm_003_codex_mount
Create Date: 2026-10-11
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "cxm_004_codex_mount_enabled"
down_revision: Union[str, None] = "cxm_003_codex_mount"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("codex_mount") as batch:
        batch.add_column(
            sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true())
        )


def downgrade() -> None:
    # A switched-off row has no meaning without the flag: it would read as mounted again.
    op.execute(sa.text("DELETE FROM codex_mount WHERE enabled = false"))
    with op.batch_alter_table("codex_mount") as batch:
        batch.drop_column("enabled")
