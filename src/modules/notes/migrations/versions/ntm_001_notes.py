"""notes: notes table

Creates ``notes`` — a document with no owner: who uses it keeps the link in a table of their own.
The column order follows the project's tail rule — ``deleted_at``, then ``created_at``,
``updated_at`` — as ``wkm_001`` does. String PK ``code`` (a bare hex of length 10);
deletion is logical (``deleted_at``).

Column widths are written out as numbers rather than taken from ``constants.py``: a revision is a
snapshot of the schema as of its date, and a constant changed some day would retroactively
rewrite an already applied migration.

Revision ID: ntm_001_notes
Revises:
Create Date: 2026-10-09
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from src.core.database.types import timestamp

revision: str = "ntm_001_notes"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_TS = timestamp()


def upgrade() -> None:
    op.create_table(
        "notes",
        sa.Column("code", sa.String(length=10), primary_key=True, nullable=False),
        sa.Column("title", sa.String(length=128), nullable=False),
        sa.Column("description", sa.String(length=512), nullable=False, server_default=sa.text("''")),
        sa.Column("body", sa.String(length=65536), nullable=False, server_default=sa.text("''")),
        sa.Column("deleted_at", _TS, nullable=True),
        sa.Column("created_at", _TS, nullable=False),
        sa.Column("updated_at", _TS, nullable=False),
    )


def downgrade() -> None:
    op.drop_table("notes")
