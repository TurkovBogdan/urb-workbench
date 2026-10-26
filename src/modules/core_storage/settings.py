"""The module's runtime settings: the cleanup term, the cleanup limit, the size ceiling.

They change from the settings page without a restart: ``on_settings_change`` hands the fresh
store to ``set_current``, and every reader asks at the moment of use. Before the first store
arrives — in the build phase, in tests that bring up no settings — the defaults apply.
"""

from __future__ import annotations

from datetime import timedelta
from typing import Any

from src.core.settings import IntField, ModuleSchema
from src.modules.core_storage.constants import (
    CLEANUP_AFTER_HOURS_DEFAULT,
    CLEANUP_LIMIT_DEFAULT,
    MAX_FILE_SIZE_MB_DEFAULT,
)

_BYTES_PER_MB = 1024 * 1024

SETTINGS_SCHEMA: ModuleSchema = (
    IntField(
        key="cleanup_after_hours",
        label="Hours before a file is removed",
        description="How long a file nobody holds waits before the cleanup task removes it from disk.",
        default_=CLEANUP_AFTER_HOURS_DEFAULT,
        min=1,
    ),
    IntField(
        key="cleanup_limit",
        label="Files per cleanup run",
        description="How many files one cleanup run removes; 0 — no limit.",
        default_=CLEANUP_LIMIT_DEFAULT,
        min=0,
    ),
    IntField(
        key="max_file_size_mb",
        label="File size ceiling, MB",
        description="The storage refuses a file larger than this.",
        default_=MAX_FILE_SIZE_MB_DEFAULT,
        min=1,
    ),
)

_current: Any = None


def set_current(store: Any) -> None:
    global _current
    _current = store


def _value(key: str, default: int) -> int:
    return default if _current is None else getattr(_current, key)


def cleanup_after() -> timedelta:
    return timedelta(hours=_value("cleanup_after_hours", CLEANUP_AFTER_HOURS_DEFAULT))


def cleanup_limit() -> int:
    """Files per cleanup run; ``0`` — no limit."""
    return _value("cleanup_limit", CLEANUP_LIMIT_DEFAULT)


def max_file_size() -> int:
    """The size ceiling in bytes."""
    return _value("max_file_size_mb", MAX_FILE_SIZE_MB_DEFAULT) * _BYTES_PER_MB


__all__ = ["SETTINGS_SCHEMA", "cleanup_after", "cleanup_limit", "max_file_size", "set_current"]
