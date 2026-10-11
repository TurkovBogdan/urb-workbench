"""codex: codex_note table

Creates ``codex_note`` — a record of a codex's tree, an adjacency list: ``codex_code`` → codex.code
and ``parent_code`` → codex_note.code, both ``ON DELETE CASCADE`` (a hard delete takes the branch
below). ``parent_code`` is ``NULL`` on the codex's top level. The path is not stored.

A slug is unique among live siblings, and that takes two partial unique indexes: a plain
``UNIQUE (parent_code, slug)`` does not compare ``NULL`` with ``NULL`` on SQLite or PostgreSQL, so
the top level is indexed by ``codex_code`` instead. ``ck_codex_note_not_own_parent`` is the one
cycle the schema can see; longer cycles, the depth limit and "the parent is in the same codex"
are the service's.

Revision ID: cxm_002_codex_note
Revises: cxm_001_codex
Create Date: 2026-10-11
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from src.core.database.types import timestamp

revision: str = "cxm_002_codex_note"
down_revision: Union[str, None] = "cxm_001_codex"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_TS = timestamp()
_LIVE_CHILD = sa.text("parent_code IS NOT NULL AND deleted_at IS NULL")
_LIVE_TOP = sa.text("parent_code IS NULL AND deleted_at IS NULL")


def upgrade() -> None:
    op.create_table(
        "codex_note",
        sa.Column("code", sa.String(length=10), primary_key=True, nullable=False),
        sa.Column("codex_code", sa.String(length=10), nullable=False),
        sa.Column("parent_code", sa.String(length=10), nullable=True),
        sa.Column("slug", sa.String(length=64), nullable=False),
        sa.Column("title", sa.String(length=128), nullable=False),
        sa.Column("description", sa.String(length=512), nullable=False, server_default=sa.text("''")),
        sa.Column("body", sa.String(length=65536), nullable=False, server_default=sa.text("''")),
        sa.Column("sort", sa.Integer(), nullable=False, server_default=sa.text("500")),
        sa.Column("deleted_at", _TS, nullable=True),
        sa.Column("created_at", _TS, nullable=False),
        sa.Column("updated_at", _TS, nullable=False),
        sa.ForeignKeyConstraint(
            ["codex_code"], ["codex.code"], name="fk_codex_note_codex_code", ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["parent_code"],
            ["codex_note.code"],
            name="fk_codex_note_parent_code",
            ondelete="CASCADE",
        ),
        sa.CheckConstraint("code <> parent_code", name="ck_codex_note_not_own_parent"),
    )
    op.create_index(
        "ux_codex_note_parent_slug",
        "codex_note",
        ["parent_code", "slug"],
        unique=True,
        sqlite_where=_LIVE_CHILD,
        postgresql_where=_LIVE_CHILD,
    )
    op.create_index(
        "ux_codex_note_top_slug",
        "codex_note",
        ["codex_code", "slug"],
        unique=True,
        sqlite_where=_LIVE_TOP,
        postgresql_where=_LIVE_TOP,
    )
    op.create_index("ix_codex_note_parent_sort", "codex_note", ["parent_code", "sort"])
    op.create_index(
        "ix_codex_note_codex_sort", "codex_note", ["codex_code", "parent_code", "sort"]
    )


def downgrade() -> None:
    op.drop_index("ix_codex_note_codex_sort", table_name="codex_note")
    op.drop_index("ix_codex_note_parent_sort", table_name="codex_note")
    op.drop_index("ux_codex_note_top_slug", table_name="codex_note")
    op.drop_index("ux_codex_note_parent_slug", table_name="codex_note")
    op.drop_table("codex_note")
