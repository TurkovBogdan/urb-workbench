"""core_storage: file owners table

Creates ``core_storage_file_owner`` — who holds a file: an opaque ``owner_type`` + ``owner_id`` +
``owner_key`` the consumer chooses, as the composite primary key with the file code. ``RESTRICT``
on the file keeps a file with any owner row from being deleted; the index on
``(owner_type, owner_id)`` releases an entity from all its files at once.
``original_filename`` + ``original_extension`` keep the name the owner brought the file under,
``''`` when it brought none. The column order follows the project's tail rule — ``deleted_at``,
then ``created_at``.

Revision ID: csm_002_file_owners
Revises: csm_001_files
Create Date: 2026-10-24
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from src.core.database.types import timestamp

revision: str = "csm_002_file_owners"
down_revision: Union[str, None] = "csm_001_files"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_TS = timestamp()


def upgrade() -> None:
    op.create_table(
        "core_storage_file_owner",
        sa.Column("file_code", sa.String(length=10), nullable=False),
        sa.Column("owner_type", sa.String(length=64), nullable=False),
        sa.Column("owner_id", sa.String(length=255), nullable=False),
        sa.Column("owner_key", sa.String(length=255), nullable=False, server_default=sa.text("''")),
        sa.Column(
            "original_filename", sa.String(length=255), nullable=False, server_default=sa.text("''")
        ),
        sa.Column(
            "original_extension", sa.String(length=16), nullable=False, server_default=sa.text("''")
        ),
        sa.Column("deleted_at", _TS, nullable=True),
        sa.Column("created_at", _TS, nullable=False),
        sa.PrimaryKeyConstraint("file_code", "owner_type", "owner_id", "owner_key"),
        sa.ForeignKeyConstraint(
            ["file_code"],
            ["core_storage_file.code"],
            name="fk_core_storage_file_owner_file_code",
            ondelete="RESTRICT",
        ),
    )
    op.create_index(
        "ix_core_storage_file_owner_owner",
        "core_storage_file_owner",
        ["owner_type", "owner_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_core_storage_file_owner_owner", table_name="core_storage_file_owner")
    op.drop_table("core_storage_file_owner")
