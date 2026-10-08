"""notes: ix_notes_deleted_updated

An index for the list of every document: filter out deleted rows, newest change first.

**A separate revision rather than part of ``ntm_001``, on purpose.** ``notes`` is the target of
the consumers' FKs (``tasks_note`` first), and ``depends_on`` may point only at a NON-head: a head
that is an ancestor of another chain's head breaks the overlap check while the state is being
read. This revision buries the creating one under itself, so ``tsm_011_note`` safely depends on
``ntm_001_notes`` — the same split as ``wkm_001`` / ``wkm_002``.

Revision ID: ntm_002_notes_list_index
Revises: ntm_001_notes
Create Date: 2026-10-09
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op

revision: str = "ntm_002_notes_list_index"
down_revision: Union[str, None] = "ntm_001_notes"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_index("ix_notes_deleted_updated", "notes", ["deleted_at", "updated_at"])


def downgrade() -> None:
    op.drop_index("ix_notes_deleted_updated", table_name="notes")
