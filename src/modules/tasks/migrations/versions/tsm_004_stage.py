"""tasks: tasks_stage table

Creates ``tasks_stage`` — a plan stage inside a task. Column order mirrors
``models/stage.py::TasksStage``. String PK ``code``; FK ``task_code`` → tasks.code
(CASCADE). ``status`` reuses the task's vocabulary and differs only in its default (``planned``):
the values are spelled out literally — a migration pins the schema as of its date and must not
change to follow ``constants.py``.

The ``(task_code, number)`` index is **unique**: it both defines the stage order and forbids two
stages of one task from sharing a number. It also covers the child side of the FK.

A stage has no soft delete: an abandoned stage is status ``canceled``, not a hidden row.

Revision ID: tsm_004_stage
Revises: tsm_003_link
Create Date: 2026-09-20
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from src.core.database.types import timestamp

revision: str = "tsm_004_stage"
down_revision: Union[str, None] = "tsm_003_link"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_TS = timestamp()


def upgrade() -> None:
    op.create_table(
        "tasks_stage",
        sa.Column("code", sa.String(length=10), primary_key=True, nullable=False),
        sa.Column("task_code", sa.String(length=10), nullable=False),
        sa.Column("number", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False, server_default=sa.text("'planned'")),
        sa.Column("title", sa.String(length=128), nullable=False),
        sa.Column("description", sa.String(length=512), nullable=False, server_default=sa.text("''")),
        sa.Column("body", sa.String(length=8192), nullable=False, server_default=sa.text("''")),
        sa.Column("evidence", sa.String(length=1024), nullable=False, server_default=sa.text("''")),
        sa.Column("started_at", _TS, nullable=True),
        sa.Column("finished_at", _TS, nullable=True),
        sa.Column("created_at", _TS, nullable=False),
        sa.Column("updated_at", _TS, nullable=False),
        sa.ForeignKeyConstraint(
            ["task_code"],
            ["tasks.code"],
            name="fk_tasks_stage_task_code",
            ondelete="CASCADE",
        ),
        sa.CheckConstraint(
            "status IN ('backlog', 'planned', 'in_progress', 'in_test', 'in_review', 'done', "
            "'canceled')",
            name="ck_tasks_stage_status",
        ),
    )
    op.create_index(
        "ix_tasks_stage_task_number", "tasks_stage", ["task_code", "number"], unique=True
    )


def downgrade() -> None:
    op.drop_index("ix_tasks_stage_task_number", table_name="tasks_stage")
    op.drop_table("tasks_stage")
