"""tasks: tasks_note table

Creates ``tasks_note`` — журнал работы: решения, замечания, находки и факты одной дописываемой
таблицей. Column order mirrors ``models/note.py::TasksNote``. String PK ``code``; FK ``task_code``
→ tasks.code (CASCADE) и ``stage_code`` → tasks_stage.code (CASCADE, nullable — запись про
задачу целиком этапа не называет).

Значения ``type`` перечислены буквально, порядок от частого к редкому. ``updated_at`` в таблице
нет намеренно: записи только дописываются, отмена оформляется новой строкой.

Два индекса: чтение журнала задачи в порядке появления и выборка записей этапа (она же покрывает
дочернюю сторону FK ``stage_code``).

Revision ID: tsm_005_note
Revises: tsm_004_stage
Create Date: 2026-09-20
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from src.core.database.types import timestamp

revision: str = "tsm_005_note"
down_revision: Union[str, None] = "tsm_004_stage"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_TS = timestamp()


def upgrade() -> None:
    op.create_table(
        "tasks_note",
        sa.Column("code", sa.String(length=10), primary_key=True, nullable=False),
        sa.Column("task_code", sa.String(length=10), nullable=False),
        sa.Column("stage_code", sa.String(length=10), nullable=True),
        sa.Column("type", sa.String(length=16), nullable=False),
        sa.Column("title", sa.String(length=128), nullable=False),
        sa.Column("body", sa.String(length=2048), nullable=False, server_default=sa.text("''")),
        sa.Column("resolution", sa.String(length=1024), nullable=False, server_default=sa.text("''")),
        sa.Column("created_at", _TS, nullable=False),
        sa.ForeignKeyConstraint(
            ["task_code"],
            ["tasks.code"],
            name="fk_tasks_note_task_code",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["stage_code"],
            ["tasks_stage.code"],
            name="fk_tasks_note_stage_code",
            ondelete="CASCADE",
        ),
        sa.CheckConstraint(
            "type IN ('decision', 'remark', 'finding', 'fact')", name="ck_tasks_note_type"
        ),
    )
    op.create_index(
        "ix_tasks_note_task_created", "tasks_note", ["task_code", "created_at"]
    )
    op.create_index("ix_tasks_note_stage", "tasks_note", ["stage_code"])


def downgrade() -> None:
    op.drop_index("ix_tasks_note_stage", table_name="tasks_note")
    op.drop_index("ix_tasks_note_task_created", table_name="tasks_note")
    op.drop_table("tasks_note")
