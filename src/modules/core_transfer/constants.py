"""Limits and fixed names of every transfer archive.

Limits are constants, not settings: a setting here would invite raising the limit instead of
finding out why an archive grew that large.
"""

from __future__ import annotations

MIMETYPE_ENTRY = "mimetype"
MANIFEST_ENTRY = "manifest.json"

MAX_UPLOAD_BYTES = 1024 * 1024 * 1024
MAX_TOTAL_UNCOMPRESSED_BYTES = 4 * 1024 * 1024 * 1024
MAX_TEXT_ENTRY_BYTES = 64 * 1024 * 1024
READ_CHUNK = 256 * 1024

# There may be no background worker at all, so the leftovers of abandoned imports are swept by the
# next upload.
UPLOAD_LIFETIME_SECONDS = 24 * 60 * 60

# What a person may choose for an entity whose code is taken here.
CHOICE_UPDATE = "update"
CHOICE_REPLACE = "replace"
CHOICES = (CHOICE_UPDATE, CHOICE_REPLACE)

INSTALL_ID_KEY = "install_id"
MODULE_NAME = "core_transfer"

__all__ = [
    "CHOICES",
    "CHOICE_REPLACE",
    "CHOICE_UPDATE",
    "INSTALL_ID_KEY",
    "MANIFEST_ENTRY",
    "MAX_TEXT_ENTRY_BYTES",
    "MAX_TOTAL_UNCOMPRESSED_BYTES",
    "MAX_UPLOAD_BYTES",
    "MIMETYPE_ENTRY",
    "MODULE_NAME",
    "READ_CHUNK",
    "UPLOAD_LIFETIME_SECONDS",
]
