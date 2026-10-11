"""codex: codex table

Creates ``codex`` — a codex: development rules on one theme, the root of its tree of notes. String
PK ``code`` (a bare hex of length 10); deletion is logical (``deleted_at``). ``ux_codex_slug`` is a
partial unique index over live rows: a deleted codex frees its slug. The tail columns follow the
project's rule — ``deleted_at``, then ``created_at``, ``updated_at``.

The table references nothing outside the module, so the chain's root needs no ``depends_on``; the
dependency on ``workspace`` sits on ``cxm_003``, the revision whose FK needs it.

Column widths are written out as numbers rather than taken from ``constants.py``: a revision is a
snapshot of the schema as of its date.

Revision ID: cxm_001_codex
Revises:
Create Date: 2026-10-11
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from src.core.database.types import timestamp

revision: str = "cxm_001_codex"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_TS = timestamp()
_LIVE = sa.text("deleted_at IS NULL")


def upgrade() -> None:
    op.create_table(
        "codex",
        sa.Column("code", sa.String(length=10), primary_key=True, nullable=False),
        sa.Column("slug", sa.String(length=64), nullable=False),
        sa.Column("title", sa.String(length=128), nullable=False),
        sa.Column("description", sa.String(length=512), nullable=False, server_default=sa.text("''")),
        sa.Column("body", sa.String(length=65536), nullable=False, server_default=sa.text("''")),
        sa.Column("sort", sa.Integer(), nullable=False, server_default=sa.text("500")),
        sa.Column("deleted_at", _TS, nullable=True),
        sa.Column("created_at", _TS, nullable=False),
        sa.Column("updated_at", _TS, nullable=False),
    )
    op.create_index(
        "ux_codex_slug",
        "codex",
        ["slug"],
        unique=True,
        sqlite_where=_LIVE,
        postgresql_where=_LIVE,
    )


def downgrade() -> None:
    op.drop_index("ux_codex_slug", table_name="codex")
    op.drop_table("codex")
