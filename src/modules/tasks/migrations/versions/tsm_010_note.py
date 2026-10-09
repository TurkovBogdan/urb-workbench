"""tasks: tasks_note — a task's notes, documents of the notes module

Creates ``tasks_note``: one row per note, naming the task it belongs to (``note_code`` is the PK),
with its position among the task's notes. Both FKs cascade: a hard-deleted task takes its rows,
and so does a hard-deleted note.

``depends_on`` points at ``ntm_001_notes``, which creates the FK target and is not the head of
its chain (``ntm_002`` sits on it) — a dependency on a head breaks the overlap check.

Revision ID: tsm_010_note
Revises: tsm_009_journal
Create Date: 2026-10-09
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from src.core.database.types import timestamp

revision: str = "tsm_010_note"
down_revision: Union[str, None] = "tsm_009_journal"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = "ntm_001_notes"

_TS = timestamp()


def upgrade() -> None:
    op.create_table(
        "tasks_note",
        sa.Column("note_code", sa.String(length=10), primary_key=True, nullable=False),
        sa.Column("task_code", sa.String(length=10), nullable=False),
        sa.Column("sort", sa.Integer(), nullable=False, server_default=sa.text("500")),
        sa.Column("created_at", _TS, nullable=False),
        sa.ForeignKeyConstraint(
            ["note_code"], ["notes.code"], name="fk_tasks_note_note_code", ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["task_code"], ["tasks.code"], name="fk_tasks_note_task_code", ondelete="CASCADE"
        ),
    )
    op.create_index("ix_tasks_note_task_sort", "tasks_note", ["task_code", "sort"])


def downgrade() -> None:
    op.drop_index("ix_tasks_note_task_sort", table_name="tasks_note")
    op.drop_table("tasks_note")
