"""tasks: tasks_file — files of core_storage bound to a task

Creates ``tasks_file``: one row per file in a task (``(task_code, file_code)`` is the PK — a file
is in a task once), the note or the stage it was attached at (at most one of the two), its title
and description in the task, and its position among the task's files. Every FK cascades: the row
goes with its task, file, note or stage. The cascade cannot release the storage owner — the
deletion functions of the module do that.

``depends_on`` points at ``csm_001_files``, which creates the FK target and is not the head of its
chain (``csm_002_file_owners`` sits on it) — a dependency on a head breaks the overlap check.

Widths are written out rather than taken from ``constants.py``: a revision is a snapshot of the
schema as of its date.

Revision ID: tsm_011_file
Revises: tsm_010_note
Create Date: 2026-10-25
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from src.core.database.types import timestamp

revision: str = "tsm_011_file"
down_revision: Union[str, None] = "tsm_010_note"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = "csm_001_files"

_TS = timestamp()


def upgrade() -> None:
    op.create_table(
        "tasks_file",
        sa.Column("task_code", sa.String(length=10), primary_key=True, nullable=False),
        sa.Column("file_code", sa.String(length=10), primary_key=True, nullable=False),
        sa.Column("note_code", sa.String(length=10), nullable=True),
        sa.Column("stage_code", sa.String(length=10), nullable=True),
        sa.Column("title", sa.String(length=256), nullable=False, server_default=sa.text("''")),
        sa.Column(
            "description", sa.String(length=256), nullable=False, server_default=sa.text("''")
        ),
        sa.Column("sort", sa.Integer(), nullable=False, server_default=sa.text("500")),
        sa.Column("created_at", _TS, nullable=False),
        sa.Column("updated_at", _TS, nullable=False),
        sa.ForeignKeyConstraint(
            ["task_code"], ["tasks.code"], name="fk_tasks_file_task_code", ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["file_code"],
            ["core_storage_file.code"],
            name="fk_tasks_file_file_code",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["note_code"], ["notes.code"], name="fk_tasks_file_note_code", ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["stage_code"],
            ["tasks_stage.code"],
            name="fk_tasks_file_stage_code",
            ondelete="CASCADE",
        ),
        sa.CheckConstraint(
            "note_code IS NULL OR stage_code IS NULL", name="ck_tasks_file_one_place"
        ),
    )
    op.create_index("ix_tasks_file_file_code", "tasks_file", ["file_code"])
    op.create_index("ix_tasks_file_note_code", "tasks_file", ["note_code"])
    op.create_index("ix_tasks_file_stage_code", "tasks_file", ["stage_code"])


def downgrade() -> None:
    op.drop_index("ix_tasks_file_stage_code", table_name="tasks_file")
    op.drop_index("ix_tasks_file_note_code", table_name="tasks_file")
    op.drop_index("ix_tasks_file_file_code", table_name="tasks_file")
    op.drop_table("tasks_file")
