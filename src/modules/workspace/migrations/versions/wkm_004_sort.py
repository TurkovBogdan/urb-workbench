"""workspace: workspaces.sort — a manual position in the list

Workspaces used to be listed by title only; now they carry a position the same way a task group
does (``tasks_group.sort``): higher ``sort`` = higher up, then title, then code. Every existing
row gets ``SORT_DEFAULT`` (500), so until someone sets a number the list keeps its old order — by
title.

The list index follows the query: ``ix_workspaces_deleted_title`` (``deleted_at``, ``title``,
``code``) is replaced by ``ix_workspaces_deleted_sort`` (``deleted_at``, ``sort``, ``title``,
``code``).

On SQLite adding a column with a server default is a plain ``ALTER TABLE ADD COLUMN`` — no table
rebuild, so the ``ON DELETE CASCADE`` children of ``workspaces`` are not involved.

Revision ID: wkm_004_sort
Revises: wkm_003_description_len
Create Date: 2026-10-07
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "wkm_004_sort"
down_revision: Union[str, None] = "wkm_003_description_len"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# ``constants.SORT_DEFAULT`` at the time of writing — a migration must not follow later edits.
_SORT_DEFAULT = 500


def upgrade() -> None:
    op.add_column(
        "workspaces",
        sa.Column(
            "sort",
            sa.Integer(),
            nullable=False,
            server_default=sa.text(str(_SORT_DEFAULT)),
        ),
    )
    op.drop_index("ix_workspaces_deleted_title", table_name="workspaces")
    op.create_index(
        "ix_workspaces_deleted_sort",
        "workspaces",
        ["deleted_at", "sort", "title", "code"],
    )


def downgrade() -> None:
    op.drop_index("ix_workspaces_deleted_sort", table_name="workspaces")
    op.create_index(
        "ix_workspaces_deleted_title",
        "workspaces",
        ["deleted_at", "title", "code"],
    )
    with op.batch_alter_table("workspaces") as batch_op:
        batch_op.drop_column("sort")
