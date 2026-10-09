"""Portable column types: one model runs on both PostgreSQL and SQLite.

PostgreSQL keeps its rich native types via ``.with_variant()``; SQLite (the zero-install
tier) falls back to the generic base. These helpers make **the migrations portable too**:
a migration that uses them (``json_value()``/``timestamp()``) runs on PostgreSQL and on
file-backed SQLite (dev) alike. ``create_all`` is left only for in-memory SQLite (the test
harness), which has no migration history.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import DateTime, JSON
from sqlalchemy.dialects.postgresql import JSONB, TIMESTAMP
from sqlalchemy.types import TypeEngine


def timestamp() -> TypeEngine[Any]:
    """Time without microseconds: PG → ``TIMESTAMP(precision=0)``, SQLite → ``DATETIME``."""
    return DateTime().with_variant(TIMESTAMP(precision=0), "postgresql")


def json_value() -> TypeEngine[Any]:
    """Structured JSON: PG → ``JSONB``, SQLite → ``JSON`` (stored as TEXT)."""
    return JSON().with_variant(JSONB(), "postgresql")


__all__ = ["json_value", "timestamp"]
