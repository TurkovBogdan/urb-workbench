"""workspace: ix_workspaces_deleted_title

An index for the module's only query (``crud/workspace.py::workspace_list``): filter out deleted
rows, then order by title with the code as a tiebreaker. The columns follow the query —
``deleted_at`` (filter), ``title``, ``code`` (sort).

**A separate revision rather than part of ``wkm_001``, on purpose.** The ``workspaces`` table is
the target of a cross-module FK from ``tasks``, and ``depends_on`` may point only at a NON-head: a
head that turns out to be an ancestor of another chain's head breaks the overlap check while the
state is still being read, and the database gets stuck. This revision buries the creating one
under itself, so ``tsm_001_group`` safely depends on ``wkm_001_workspaces``. The technique is
described in ``conventions/db-migrations.md`` — "split the producing migration so the part that
creates the referenced object becomes a non-head".

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
