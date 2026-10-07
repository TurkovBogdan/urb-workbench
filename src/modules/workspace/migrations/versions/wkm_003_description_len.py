"""workspace: workspaces.description narrowed to 128

A workspace's description is a line under its name in the cards and the switcher; 512 let it grow
into a paragraph. The column narrows to ``String(128)`` (``constants.DESCRIPTION_MAX``) — the same
limit and the same reasoning as ``tsm_006_group_description_len`` for a task group.

The data is clipped FIRST, in the same revision: SQLite does not enforce ``VARCHAR(n)``, so a
narrowed column would keep its long values and only PostgreSQL would ever refuse them — and on
PostgreSQL the ``ALTER`` itself fails while a longer value is still there. ``substr``/``length``
count characters on both providers, which is what the model's limit means.

The clipped tail is lost: there is no downgrade that brings it back, only the column width.

On SQLite the width change rebuilds ``workspaces`` (batch mode). It is the parent of every
module's ``workspace_code`` with ``ON DELETE CASCADE``; the rebuild's ``DROP TABLE`` would fire
that cascade and empty every workspace, so it relies on the runner turning foreign keys off around
the migration (``core/database/sqlite.py::foreign_keys_disabled``), which also checks for
violations after.

Revision ID: wkm_003_description_len
Revises: wkm_002_workspaces_list_index
Create Date: 2026-10-07
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "wkm_003_description_len"
down_revision: Union[str, None] = "wkm_002_workspaces_list_index"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_NEW = 128
_OLD = 512


def upgrade() -> None:
    op.execute(
        sa.text(
            "UPDATE workspaces SET description = substr(description, 1, :limit) "
            "WHERE length(description) > :limit"
        ).bindparams(limit=_NEW)
    )
    with op.batch_alter_table("workspaces") as batch_op:
        batch_op.alter_column(
            "description",
            existing_type=sa.String(length=_OLD),
            type_=sa.String(length=_NEW),
            existing_nullable=False,
            existing_server_default=sa.text("''"),
        )


def downgrade() -> None:
    with op.batch_alter_table("workspaces") as batch_op:
        batch_op.alter_column(
            "description",
            existing_type=sa.String(length=_NEW),
            type_=sa.String(length=_OLD),
            existing_nullable=False,
            existing_server_default=sa.text("''"),
        )
