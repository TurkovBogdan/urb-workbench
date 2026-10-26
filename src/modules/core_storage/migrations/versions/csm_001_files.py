"""core_storage: files table

Creates ``core_storage_file`` — a stored file: the bytes in one of the stores and what they are.
The dedup key ``UNIQUE (store, sha256)`` covers soft-deleted rows too; the index on
``deleted_at`` serves the cleanup task. The column order follows the project's tail rule —
``deleted_at``, then ``created_at``.

Column widths and the category list are written out rather than taken from ``constants.py``:
a revision is a snapshot of the schema as of its date.

The two tables of the module are split one per revision, so this one stops being a head by
itself: a consumer keeping an FK on ``core_storage_file.code`` names it in ``depends_on``.

Revision ID: csm_001_files
Revises:
Create Date: 2026-10-24
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from src.core.database.types import timestamp

revision: str = "csm_001_files"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_TS = timestamp()

_TYPE_CHECK = (
    "type IN ('image', 'document', 'table', 'presentation', 'text', 'archive', 'video', "
    "'font', 'key', 'email', 'other')"
)


def upgrade() -> None:
    op.create_table(
        "core_storage_file",
        sa.Column("code", sa.String(length=10), primary_key=True, nullable=False),
        sa.Column("store", sa.String(length=32), nullable=False),
        sa.Column("sha256", sa.String(length=64), nullable=False),
        sa.Column("type", sa.String(length=16), nullable=False),
        sa.Column("size", sa.BigInteger(), nullable=False),
        sa.Column("mime", sa.String(length=127), nullable=False),
        sa.Column("extension", sa.String(length=16), nullable=False),
        sa.Column("deleted_at", _TS, nullable=True),
        sa.Column("created_at", _TS, nullable=False),
        sa.UniqueConstraint("store", "sha256", name="uq_core_storage_file_store_sha256"),
        sa.CheckConstraint(_TYPE_CHECK, name="ck_core_storage_file_type"),
    )
    op.create_index("ix_core_storage_file_deleted_at", "core_storage_file", ["deleted_at"])


def downgrade() -> None:
    op.drop_index("ix_core_storage_file_deleted_at", table_name="core_storage_file")
    op.drop_table("core_storage_file")
