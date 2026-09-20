"""tasks: tasks_link table

Creates ``tasks_link`` — ребро дерева задач. Column order mirrors ``models/link.py::TasksLink``.
``task_code`` — одновременно PK и FK → tasks.code (CASCADE): одна строка на задачу, второго
родителя схема физически не вмещает. ``parent_code`` — FK туда же (CASCADE, nullable; ``NULL`` =
корень пространства). Дети родителя идут одним полотном: весь порядок несёт ``sort``. Индекс
``(parent_code, sort)`` отдаёт детей узла уже упорядоченными и покрывает дочернюю сторону FK
``parent_code``.

Revision ID: tsm_003_link
Revises: tsm_002_task
Create Date: 2026-09-20
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from src.core.database.types import timestamp

revision: str = "tsm_003_link"
down_revision: Union[str, None] = "tsm_002_task"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_TS = timestamp()


def upgrade() -> None:
    op.create_table(
        "tasks_link",
        sa.Column("task_code", sa.String(length=10), primary_key=True, nullable=False),
        sa.Column("parent_code", sa.String(length=10), nullable=True),
        sa.Column("sort", sa.Integer(), nullable=False, server_default=sa.text("500")),
        sa.Column("updated_at", _TS, nullable=False),
        sa.ForeignKeyConstraint(
            ["task_code"],
            ["tasks.code"],
            name="fk_tasks_link_task_code",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["parent_code"],
            ["tasks.code"],
            name="fk_tasks_link_parent_code",
            ondelete="CASCADE",
        ),
    )
    op.create_index("ix_tasks_link_parent_sort", "tasks_link", ["parent_code", "sort"])


def downgrade() -> None:
    op.drop_index("ix_tasks_link_parent_sort", table_name="tasks_link")
    op.drop_table("tasks_link")
