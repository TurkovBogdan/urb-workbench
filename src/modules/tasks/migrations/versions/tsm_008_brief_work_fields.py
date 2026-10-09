"""tasks: constraints and criteria widened to 2048, body renamed to plan, new progress and result

Two changes to ``tasks`` that shipped together, so the table is rebuilt once on SQLite:

**The brief lists widen to 2048.** Both fields are lists — what may and may not be touched, and
the conditions of done, each with what proves it — and 1024 characters cut a real brief short. The
columns widen to ``String(2048)`` (``constants.CONSTRAINTS_MAX`` / ``CRITERIA_MAX``). Widening keeps
every value as it is, so the upgrade touches no data. The downgrade narrows back and must clip
FIRST, for the reason ``tsm_006`` gives: PostgreSQL refuses the ``ALTER`` while a longer value is
still there. The clipped tail is lost.

**The agent's work is three fields.** One question each: ``plan`` — the intent, written before the
code changes; ``progress`` — the course, a diary kept along the way; ``result`` — the outcome,
written at hand-over. ``body`` stopped saying which of them it is, so the plan takes its own name.
The ``body`` of a stage and of a journal entry stays: there it is the only text. The rename keeps
every plan as it is. The two new columns go right after ``plan`` — the text block of a task reads
in the order the work goes. That holds on SQLite, where batch mode rebuilds the table and can
place a column; PostgreSQL appends them at the end, and nothing reads by position. The downgrade
drops ``progress`` and ``result`` with whatever was written there, and renames ``plan`` back.

On SQLite the change rebuilds ``tasks`` (batch mode). It is the parent of ``tasks_link``,
``tasks_stage`` and ``tasks_note`` with ``ON DELETE CASCADE``; the rebuild's ``DROP TABLE`` would
fire that cascade, so it relies on the runner turning foreign keys off around the migration
(``core/database/sqlite.py::foreign_keys_disabled``), which also checks for violations after.

Revision ID: tsm_008_brief_work_fields
Revises: tsm_007_codes_upper
Create Date: 2026-10-08
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "tsm_008_brief_work_fields"
down_revision: Union[str, None] = "tsm_007_codes_upper"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_BRIEF_LISTS = ("constraints", "criteria")
_BRIEF_LISTS_NEW = 2048
_BRIEF_LISTS_OLD = 1024
_PLAN_MAX = 8192
_PROGRESS_MAX = 16384
_RESULT_MAX = 2048


def _placed(anchor: str) -> dict[str, str]:
    """Where a new column goes — on SQLite only.

    Placement exists only when batch mode rebuilds the table; PostgreSQL alters in place, and
    alembic refuses ``insert_after`` there outright instead of ignoring it.
    """
    return {"insert_after": anchor} if op.get_bind().dialect.name == "sqlite" else {}


def _set_brief_lists_width(batch_op, old: int, new: int) -> None:
    for column in _BRIEF_LISTS:
        batch_op.alter_column(
            column,
            existing_type=sa.String(length=old),
            type_=sa.String(length=new),
            existing_nullable=False,
            existing_server_default=sa.text("''"),
        )


def upgrade() -> None:
    with op.batch_alter_table("tasks") as batch_op:
        _set_brief_lists_width(batch_op, _BRIEF_LISTS_OLD, _BRIEF_LISTS_NEW)
        batch_op.alter_column(
            "body",
            new_column_name="plan",
            existing_type=sa.String(length=_PLAN_MAX),
            existing_nullable=False,
            existing_server_default=sa.text("''"),
        )
        batch_op.add_column(
            sa.Column(
                "progress",
                sa.String(length=_PROGRESS_MAX),
                nullable=False,
                server_default=sa.text("''"),
            ),
            # Batch ordering is keyed by the names the table had before this migration, so the
            # anchor is the old name of the column renamed above.
            **_placed("body"),
        )
        batch_op.add_column(
            sa.Column(
                "result",
                sa.String(length=_RESULT_MAX),
                nullable=False,
                server_default=sa.text("''"),
            ),
            **_placed("progress"),
        )


def downgrade() -> None:
    for column in _BRIEF_LISTS:
        op.execute(
            sa.text(
                f"UPDATE tasks SET {column} = substr({column}, 1, :limit) "
                f"WHERE length({column}) > :limit"
            ).bindparams(limit=_BRIEF_LISTS_OLD)
        )
    with op.batch_alter_table("tasks") as batch_op:
        batch_op.drop_column("result")
        batch_op.drop_column("progress")
        batch_op.alter_column(
            "plan",
            new_column_name="body",
            existing_type=sa.String(length=_PLAN_MAX),
            existing_nullable=False,
            existing_server_default=sa.text("''"),
        )
        _set_brief_lists_width(batch_op, _BRIEF_LISTS_NEW, _BRIEF_LISTS_OLD)
