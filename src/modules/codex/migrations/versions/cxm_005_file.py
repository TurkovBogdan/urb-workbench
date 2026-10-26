"""codex: codex_file — files of core_storage bound to a codex note

Creates ``codex_file``: one row per file in a note (``(note_code, file_code)`` is the PK — a file
is in a note once), its title and description there, and its position among the note's files. The
holder is a note, never a codex: the FK points at ``codex_note``. Both FKs cascade; the cascade
cannot release the storage owner — the module's hard deletions do that.

``depends_on`` points at ``csm_001_files``, which creates the FK target and is not the head of its
chain (``csm_002_file_owners`` sits on it) — a dependency on a head breaks the overlap check.

Widths are written out rather than taken from ``constants.py``: a revision is a snapshot of the
schema as of its date.

Revision ID: cxm_005_file
Revises: cxm_004_codex_mount_enabled
Create Date: 2026-10-25
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from src.core.database.types import timestamp

revision: str = "cxm_005_file"
down_revision: Union[str, None] = "cxm_004_codex_mount_enabled"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = "csm_001_files"

_TS = timestamp()


def upgrade() -> None:
    op.create_table(
        "codex_file",
        sa.Column("note_code", sa.String(length=10), primary_key=True, nullable=False),
        sa.Column("file_code", sa.String(length=10), primary_key=True, nullable=False),
        sa.Column("title", sa.String(length=256), nullable=False, server_default=sa.text("''")),
        sa.Column(
            "description", sa.String(length=256), nullable=False, server_default=sa.text("''")
        ),
        sa.Column("sort", sa.Integer(), nullable=False, server_default=sa.text("500")),
        sa.Column("created_at", _TS, nullable=False),
        sa.Column("updated_at", _TS, nullable=False),
        sa.ForeignKeyConstraint(
            ["note_code"], ["codex_note.code"], name="fk_codex_file_note_code", ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["file_code"],
            ["core_storage_file.code"],
            name="fk_codex_file_file_code",
            ondelete="CASCADE",
        ),
    )
    op.create_index("ix_codex_file_file_code", "codex_file", ["file_code"])


def downgrade() -> None:
    op.drop_index("ix_codex_file_file_code", table_name="codex_file")
    op.drop_table("codex_file")
