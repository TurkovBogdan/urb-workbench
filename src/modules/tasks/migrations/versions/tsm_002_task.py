"""tasks: tasks table

Creates ``tasks`` — сама задача; таблица названа по модулю, без приставки (её несут спутники:
``tasks_group``, ``tasks_link``, ``tasks_stage``, ``tasks_note``). Column order mirrors
``models/task.py::TasksTask``.
String PK ``code``; FK ``workspace_code`` → workspaces.code (CASCADE) и ``group_code`` →
tasks_group.code (SET NULL, nullable). Справочные колонки ``type``/``status``/``priority``/
``created_by`` — строки с именованными CHECK, а не нативный enum: ``CREATE TYPE`` не существует
на SQLite, а цепочка катится на обоих провайдерах. Значения CHECK перечислены буквально —
миграция фиксирует состояние схемы на своей дате и не должна меняться задним числом вслед за
``constants.py``. Три индекса — под доску по статусу, раскладку по группам и план по срокам; все
ведут с ``workspace_code`` (поперёк пространств модуль не читает).

Назначаемая дата одна — ``deadline_at``: «день, на который задача поставлена в календарь» не
завёл себе ни одного читателя и в схему не попадает вовсе.

Текст разложен по владельцу: постановку (``description`` — цель, ``context``, ``constraints``,
``criteria``) пишет человек, ``body`` — план агента, и потому он замыкает текстовый блок.

Revision ID: tsm_002_task
Revises: tsm_001_group
Create Date: 2026-09-20
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from src.core.database.types import timestamp

revision: str = "tsm_002_task"
down_revision: Union[str, None] = "tsm_001_group"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_TS = timestamp()


def upgrade() -> None:
    op.create_table(
        "tasks",
        sa.Column("code", sa.String(length=10), primary_key=True, nullable=False),
        sa.Column("workspace_code", sa.String(length=10), nullable=False),
        sa.Column("group_code", sa.String(length=10), nullable=True),
        sa.Column("type", sa.String(length=16), nullable=False, server_default=sa.text("'simple'")),
        sa.Column("status", sa.String(length=16), nullable=False, server_default=sa.text("'backlog'")),
        sa.Column("priority", sa.String(length=16), nullable=False, server_default=sa.text("'normal'")),
        sa.Column("title", sa.String(length=128), nullable=False),
        sa.Column("description", sa.String(length=512), nullable=False, server_default=sa.text("''")),
        sa.Column("context", sa.String(length=4048), nullable=False, server_default=sa.text("''")),
        sa.Column("constraints", sa.String(length=1024), nullable=False, server_default=sa.text("''")),
        sa.Column("criteria", sa.String(length=1024), nullable=False, server_default=sa.text("''")),
        sa.Column("body", sa.String(length=8192), nullable=False, server_default=sa.text("''")),
        sa.Column("deadline_at", _TS, nullable=True),
        sa.Column("started_at", _TS, nullable=True),
        sa.Column("completed_at", _TS, nullable=True),
        sa.Column("canceled_at", _TS, nullable=True),
        sa.Column("deleted_at", _TS, nullable=True),
        sa.Column("created_by", sa.String(length=16), nullable=False, server_default=sa.text("'human'")),
        sa.Column("created_at", _TS, nullable=False),
        sa.Column("updated_at", _TS, nullable=False),
        sa.ForeignKeyConstraint(
            ["workspace_code"],
            ["workspaces.code"],
            name="fk_tasks_workspace_code",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["group_code"],
            ["tasks_group.code"],
            name="fk_tasks_group_code",
            ondelete="SET NULL",
        ),
        sa.CheckConstraint(
            "type IN ('simple', 'standard', 'extended')", name="ck_tasks_type"
        ),
        sa.CheckConstraint(
            "status IN ('backlog', 'planned', 'in_progress', 'in_test', 'in_review', 'done', "
            "'canceled')",
            name="ck_tasks_status",
        ),
        sa.CheckConstraint(
            "priority IN ('burning', 'high', 'normal', 'low', 'frozen')",
            name="ck_tasks_priority",
        ),
        sa.CheckConstraint(
            "created_by IN ('human', 'agent')", name="ck_tasks_created_by"
        ),
    )
    op.create_index(
        "ix_tasks_workspace_status", "tasks", ["workspace_code", "status"]
    )
    op.create_index(
        "ix_tasks_workspace_group", "tasks", ["workspace_code", "group_code"]
    )
    op.create_index(
        "ix_tasks_workspace_deadline",
        "tasks",
        ["workspace_code", "deadline_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_tasks_workspace_deadline", table_name="tasks")
    op.drop_index("ix_tasks_workspace_group", table_name="tasks")
    op.drop_index("ix_tasks_workspace_status", table_name="tasks")
    op.drop_table("tasks")
