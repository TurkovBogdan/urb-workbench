"""workspace: workspaces table

Создаёт ``workspaces`` — рабочее пространство, верхний уровень изоляции данных. Порядок колонок
повторяет ``models/workspace.py::Workspace``. String PK ``code`` (голый hex длиной ``CODE_LEN``);
удаление логическое (``deleted_at``). Единственная ревизия цепочки модуля.

Таблица названа по сущности во множественном числе, без приставки имени модуля: модуль и
сущность здесь — одно и то же, и ``workspace_workspace`` было бы заиканием ради схемы именования.
Приставку несут таблицы модулей, где сущностей несколько (``tasks_group``, ``tasks_task``) — там
она и отвечает на вопрос «чьё это», а здесь на него отвечает само имя.

Ширины колонок выписаны числами, а не взяты из ``constants.py``: ревизия — это снимок схемы на
свою дату, и константа, которую однажды поменяют, задним числом переписала бы уже накаченную
миграцию. Совпадение с константами стерегут ``db``-тесты, сверяющие модели со схемой.

Revision ID: wkm_001_workspaces
Revises:
Create Date: 2026-09-20
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from src.core.database.types import timestamp

revision: str = "wkm_001_workspaces"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_TS = timestamp()


def upgrade() -> None:
    op.create_table(
        "workspaces",
        sa.Column("code", sa.String(length=10), primary_key=True, nullable=False),
        sa.Column("title", sa.String(length=96), nullable=False),
        sa.Column("description", sa.String(length=512), nullable=False, server_default=sa.text("''")),
        sa.Column("color", sa.String(length=32), nullable=False, server_default=sa.text("''")),
        sa.Column("icon", sa.String(length=64), nullable=False, server_default=sa.text("''")),
        sa.Column("deleted_at", _TS, nullable=True),
        sa.Column("created_at", _TS, nullable=False),
        sa.Column("updated_at", _TS, nullable=False),
    )


def downgrade() -> None:
    op.drop_table("workspaces")
