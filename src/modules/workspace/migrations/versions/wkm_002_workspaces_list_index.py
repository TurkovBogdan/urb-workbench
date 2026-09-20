"""workspace: ix_workspaces_deleted_title

Индекс под единственную выборку модуля (``crud/workspace.py::workspace_list``): отсев удалённых,
затем порядок по названию с кодом как тайбрейком. Колонки идут в порядке запроса —
``deleted_at`` (фильтр), ``title``, ``code`` (сортировка).

**Отдельной ревизией, а не внутри ``wkm_001``, намеренно.** Таблица ``workspaces`` — цель
кросс-модульного FK из ``tasks``, а ссылаться ``depends_on`` можно только на НЕ-голову: голова,
оказавшаяся предком чужой головы, роняет проверку пересечения ещё на чтении состояния, и база
встаёт колом. Эта ревизия хоронит создающую под собой, и ``tsm_001_group`` безопасно зависит от
``wkm_001_workspaces``. Приём описан в ``conventions/db-migrations.md`` — «split the producing
migration so the part that creates the referenced object becomes a non-head».

Revision ID: wkm_002_workspaces_list_index
Revises: wkm_001_workspaces
Create Date: 2026-09-20
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op

revision: str = "wkm_002_workspaces_list_index"
down_revision: Union[str, None] = "wkm_001_workspaces"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_index(
        "ix_workspaces_deleted_title",
        "workspaces",
        ["deleted_at", "title", "code"],
    )


def downgrade() -> None:
    op.drop_index("ix_workspaces_deleted_title", table_name="workspaces")
