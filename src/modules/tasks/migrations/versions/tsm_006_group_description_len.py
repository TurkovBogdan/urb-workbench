"""tasks: tasks_group.description narrowed to 128

A group's description is a one-line boundary under its name in the list cards; 512 let it grow
into a paragraph. The column narrows to ``String(128)`` (``constants.GROUP_DESCRIPTION_MAX``).

The data is clipped FIRST, in the same revision: SQLite does not enforce ``VARCHAR(n)``, so a
narrowed column would keep its long values and only PostgreSQL would ever refuse them — and on
PostgreSQL the ``ALTER`` itself fails while a longer value is still there. ``substr``/``length``
count characters on both providers, which is what the model's limit means.

The clipped tail is lost: there is no downgrade that brings it back, only the column width.

On SQLite the width change rebuilds ``tasks_group`` (batch mode). It is the parent of
``tasks.group_code`` with ``ON DELETE SET NULL``; the rebuild's ``DROP TABLE`` would fire that
action on every task, so it relies on the runner turning foreign keys off around the migration
(``core/database/sqlite.py::foreign_keys_disabled``), which also checks for violations after.

Revision ID: tsm_006_group_description_len
Revises: tsm_005_note
Create Date: 2026-10-07
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "tsm_006_group_description_len"
down_revision: Union[str, None] = "tsm_005_note"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_NEW = 128
_OLD = 512


def upgrade() -> None:
    op.execute(
        sa.text(
            "UPDATE tasks_group SET description = substr(description, 1, :limit) "
            "WHERE length(description) > :limit"
        ).bindparams(limit=_NEW)
    )
    with op.batch_alter_table("tasks_group") as batch_op:
        batch_op.alter_column(
            "description",
            existing_type=sa.String(length=_OLD),
            type_=sa.String(length=_NEW),
            existing_nullable=False,
            existing_server_default=sa.text("''"),
        )


def downgrade() -> None:
    with op.batch_alter_table("tasks_group") as batch_op:
        batch_op.alter_column(
            "description",
            existing_type=sa.String(length=_NEW),
            type_=sa.String(length=_OLD),
            existing_nullable=False,
            existing_server_default=sa.text("''"),
        )
