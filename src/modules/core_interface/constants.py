"""Limits and log channel of the core_interface module."""

from __future__ import annotations

LOG_CHANNEL = "core_interface"

# Matches the ``core_interface_settings.key`` column: a key that is too long must be rejected
# by the registry check, not fail on insert into Postgres (SQLite ignores the length, so in dev
# the defect would go unnoticed).
KEY_MAX_LENGTH = 128

VALUE_MAX_BYTES = 4096

__all__ = ["LOG_CHANNEL", "KEY_MAX_LENGTH", "VALUE_MAX_BYTES"]
