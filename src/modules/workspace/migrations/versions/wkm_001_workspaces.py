"""workspace: workspaces table

Creates ``workspaces`` — a workspace, the top level of data isolation. The column order mirrors
``models/workspace.py::Workspace``. String PK ``code`` (a bare hex of length ``CODE_LEN``);
deletion is logical (``deleted_at``). The only revision in the module's chain.

The table is named after the entity in the plural, without the module-name prefix: the module
and the entity are one and the same here, and ``workspace_workspace`` would be a stutter for the
sake of a naming scheme. The prefix is carried by tables of modules with several entities
(``tasks_group``, ``tasks_task``) — there it answers "whose is this", while here the name itself
answers it.

Column widths are written out as numbers rather than taken from ``constants.py``: a revision is a
snapshot of the schema as of its date, and a constant changed some day would retroactively
rewrite an already applied migration. Agreement with the constants is guarded by the ``db``
tests that compare the models with the schema.

Revision ID: wkm_001_workspaces
Revises:
Create Date: 2026-09-20
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from src.core.database.types import timestamp

revision: str = "wkm_001_workspaces"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_TS = timestamp()


def upgrade() -> None:
    op.create_table(
        "workspaces",
        sa.Column("code", sa.String(length=10), primary_key=True, nullable=False),
        sa.Column("title", sa.String(length=96), nullable=False),
        sa.Column("description", sa.String(length=512), nullable=False, server_default=sa.text("''")),
        sa.Column("color", sa.String(length=32), nullable=False, server_default=sa.text("''")),
        sa.Column("icon", sa.String(length=64), nullable=False, server_default=sa.text("''")),
        sa.Column("deleted_at", _TS, nullable=True),
        sa.Column("created_at", _TS, nullable=False),
        sa.Column("updated_at", _TS, nullable=False),
    )


def downgrade() -> None:
    op.drop_table("workspaces")
