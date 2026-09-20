"""tasks: tasks_group table

Creates ``tasks_group`` — группа задач в пространстве (биллинг / интерфейс / инфраструктура).
Column order mirrors ``models/group.py::TasksGroup``. String PK ``code``; FK ``workspace_code`` →
workspaces.code (CASCADE) с индексом на дочерней стороне; ``sort`` — порядок в интерфейсе
(больший выше); удаление логическое.

Первая ревизия цепочки модуля: пространство ему не принадлежит и создаётся своим модулем.
``depends_on`` указывает на ту ревизию — цель FK обязана существовать к моменту создания
таблицы, а порядок между ветками не определён ничем, кроме ``depends_on``.

Revision ID: tsm_001_group
Revises:
Create Date: 2026-09-20
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from src.core.database.types import timestamp

revision: str = "tsm_001_group"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = "wkm_001_workspaces"

_TS = timestamp()


def upgrade() -> None:
    op.create_table(
        "tasks_group",
        sa.Column("code", sa.String(length=10), primary_key=True, nullable=False),
        sa.Column("workspace_code", sa.String(length=10), nullable=False),
        sa.Column("title", sa.String(length=128), nullable=False),
        sa.Column("description", sa.String(length=512), nullable=False, server_default=sa.text("''")),
        sa.Column("color", sa.String(length=32), nullable=False, server_default=sa.text("''")),
        sa.Column("icon", sa.String(length=64), nullable=False, server_default=sa.text("''")),
        sa.Column("sort", sa.Integer(), nullable=False, server_default=sa.text("500")),
        sa.Column("deleted_at", _TS, nullable=True),
        sa.Column("created_at", _TS, nullable=False),
        sa.Column("updated_at", _TS, nullable=False),
        sa.ForeignKeyConstraint(
            ["workspace_code"],
            ["workspaces.code"],
            name="fk_tasks_group_workspace_code",
            ondelete="CASCADE",
        ),
    )
    op.create_index("ix_tasks_group_workspace_code", "tasks_group", ["workspace_code"])


def downgrade() -> None:
    op.drop_index("ix_tasks_group_workspace_code", table_name="tasks_group")
    op.drop_table("tasks_group")
