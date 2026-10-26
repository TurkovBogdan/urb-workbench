"""core_storage_upload: upload requests table

Creates ``core_storage_upload_request`` — an upload a client asked for and has not sent yet: the
sha256 of its token as the key, the holder's and the workspace's codes, the name hint, the opaque
``payload`` the holder gets, ``claimed_at`` while an upload is in flight, the expiry and the
creation time. The index on ``expires_at`` serves the cleanup. The column order follows the
project's tail rule — ``created_at`` last.

Column widths are written out rather than taken from ``constants.py``: a revision is a snapshot of
the schema as of its date. The JSON column is the core's portable type — ``JSONB`` on PostgreSQL,
``JSON`` as text on SQLite.

Revision ID: csu_001_request
Revises:
Create Date: 2026-10-26
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from src.core.database.types import json_value, timestamp

revision: str = "csu_001_request"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_TS = timestamp()


def upgrade() -> None:
    op.create_table(
        "core_storage_upload_request",
        sa.Column("token_hash", sa.String(length=64), primary_key=True, nullable=False),
        sa.Column("holder", sa.String(length=64), nullable=False),
        sa.Column("workspace_code", sa.String(length=64), nullable=False),
        sa.Column("filename", sa.String(length=272), nullable=False, server_default=""),
        sa.Column("payload", json_value(), nullable=False),
        sa.Column("claimed_at", _TS, nullable=True),
        sa.Column("expires_at", _TS, nullable=False),
        sa.Column("created_at", _TS, nullable=False),
    )
    op.create_index(
        "ix_core_storage_upload_request_expires_at",
        "core_storage_upload_request",
        ["expires_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_core_storage_upload_request_expires_at", table_name="core_storage_upload_request"
    )
    op.drop_table("core_storage_upload_request")
