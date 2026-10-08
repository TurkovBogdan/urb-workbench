"""tasks: tasks.constraints and tasks.criteria widened to 2048

Both fields are lists — what may and may not be touched, and the conditions of done, each with
what proves it — and 1024 characters cut a real brief short. The columns widen to
``String(2048)`` (``constants.CONSTRAINTS_MAX`` / ``CRITERIA_MAX``).

Widening keeps every value as it is, so the upgrade touches no data. The downgrade narrows back
and must clip FIRST, for the reason ``tsm_006`` gives: PostgreSQL refuses the ``ALTER`` while a
longer value is still there. The clipped tail is lost.

On SQLite the width change rebuilds ``tasks`` (batch mode). It is the parent of ``tasks_link``,
``tasks_stage`` and ``tasks_note`` with ``ON DELETE CASCADE``; the rebuild's ``DROP TABLE`` would
fire that cascade, so it relies on the runner turning foreign keys off around the migration
(``core/database/sqlite.py::foreign_keys_disabled``), which also checks for violations after.

Revision ID: tsm_008_brief_lists_len
Revises: tsm_007_codes_upper
Create Date: 2026-10-08
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "tsm_008_brief_lists_len"
down_revision: Union[str, None] = "tsm_007_codes_upper"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_COLUMNS = ("constraints", "criteria")
_NEW = 2048
_OLD = 1024


def _set_width(old: int, new: int) -> None:
    with op.batch_alter_table("tasks") as batch_op:
        for column in _COLUMNS:
            batch_op.alter_column(
                column,
                existing_type=sa.String(length=old),
                type_=sa.String(length=new),
                existing_nullable=False,
                existing_server_default=sa.text("''"),
            )


def upgrade() -> None:
    _set_width(_OLD, _NEW)


def downgrade() -> None:
    for column in _COLUMNS:
        op.execute(
            sa.text(
                f"UPDATE tasks SET {column} = substr({column}, 1, :limit) "
                f"WHERE length({column}) > :limit"
            ).bindparams(limit=_OLD)
        )
    _set_width(_NEW, _OLD)
