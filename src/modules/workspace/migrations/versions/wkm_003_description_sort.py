"""workspace: workspaces.description narrowed to 128, workspaces.sort — a manual position

Two changes to ``workspaces`` that shipped together, so the table is rebuilt once on SQLite:

**The description narrows to 128.** It is a line under the name in the cards and the switcher;
512 let it grow into a paragraph. The column narrows to ``String(128)``
(``constants.DESCRIPTION_MAX``) — the same limit and the same reasoning as
``tsm_006_group_description_len`` for a task group. The data is clipped FIRST, in the same
revision: SQLite does not enforce ``VARCHAR(n)``, so a narrowed column would keep its long values
and only PostgreSQL would ever refuse them — and on PostgreSQL the ``ALTER`` itself fails while a
longer value is still there. ``substr``/``length`` count characters on both providers, which is
what the model's limit means. The clipped tail is lost: there is no downgrade that brings it back,
only the column width.

**A manual position.** Workspaces used to be listed by title only; now they carry a position the
same way a task group does (``tasks_group.sort``): higher ``sort`` = higher up, then title, then
code. Every existing row gets ``SORT_DEFAULT`` (500), so until someone sets a number the list keeps
its old order — by title. The column goes right after ``icon``, as the model declares it; that
holds on SQLite, where batch mode rebuilds the table and can place a column; PostgreSQL appends it
at the end, and nothing reads by position. The list index follows the query:
``ix_workspaces_deleted_title`` (``deleted_at``, ``title``, ``code``) is replaced by
``ix_workspaces_deleted_sort`` (``deleted_at``, ``sort``, ``title``, ``code``).

On SQLite the change rebuilds ``workspaces`` (batch mode). It is the parent of every module's
``workspace_code`` with ``ON DELETE CASCADE``; the rebuild's ``DROP TABLE`` would fire that cascade
and empty every workspace, so it relies on the runner turning foreign keys off around the migration
(``core/database/sqlite.py::foreign_keys_disabled``), which also checks for violations after.

Revision ID: wkm_003_description_sort
Revises: wkm_002_workspaces_list_index
Create Date: 2026-10-07
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "wkm_003_description_sort"
down_revision: Union[str, None] = "wkm_002_workspaces_list_index"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_NEW = 128
_OLD = 512
# ``constants.SORT_DEFAULT`` at the time of writing — a migration must not follow later edits.
_SORT_DEFAULT = 500


def _placed(anchor: str) -> dict[str, str]:
    """Where a new column goes — on SQLite only.

    Placement exists only when batch mode rebuilds the table; PostgreSQL alters in place, and
    alembic refuses ``insert_after`` there outright instead of ignoring it.
    """
    return {"insert_after": anchor} if op.get_bind().dialect.name == "sqlite" else {}


def upgrade() -> None:
    op.execute(
        sa.text(
            "UPDATE workspaces SET description = substr(description, 1, :limit) "
            "WHERE length(description) > :limit"
        ).bindparams(limit=_NEW)
    )
    op.drop_index("ix_workspaces_deleted_title", table_name="workspaces")
    with op.batch_alter_table("workspaces") as batch_op:
        batch_op.alter_column(
            "description",
            existing_type=sa.String(length=_OLD),
            type_=sa.String(length=_NEW),
            existing_nullable=False,
            existing_server_default=sa.text("''"),
        )
        batch_op.add_column(
            sa.Column(
                "sort",
                sa.Integer(),
                nullable=False,
                server_default=sa.text(str(_SORT_DEFAULT)),
            ),
            **_placed("icon"),
        )
    op.create_index(
        "ix_workspaces_deleted_sort",
        "workspaces",
        ["deleted_at", "sort", "title", "code"],
    )


def downgrade() -> None:
    op.drop_index("ix_workspaces_deleted_sort", table_name="workspaces")
    with op.batch_alter_table("workspaces") as batch_op:
        batch_op.drop_column("sort")
        batch_op.alter_column(
            "description",
            existing_type=sa.String(length=_NEW),
            type_=sa.String(length=_OLD),
            existing_nullable=False,
            existing_server_default=sa.text("''"),
        )
    op.create_index(
        "ix_workspaces_deleted_title",
        "workspaces",
        ["deleted_at", "title", "code"],
    )
