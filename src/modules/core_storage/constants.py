"""Constants of the file storage: code length, column widths, file categories, defaults.

Widths live here, not in the models, because the tests build the schema with ``create_all``
from the models while the migrations spell the same widths out as numbers — a revision is a
snapshot of its date. Keeping the source of the numbers in one file keeps the two in step.
"""

from __future__ import annotations

CODE_LEN = 10

# The one place that names the module's log channel.
LOG_CHANNEL = "core_storage"

# A store code is a folder name inside the storage root and the value of ``store``.
STORE_MAX = 32
SHA256_LEN = 64
MIME_MAX = 127
EXTENSION_MAX = 16
TYPE_MAX = 16
OWNER_TYPE_MAX = 64
OWNER_ID_MAX = 255
OWNER_KEY_MAX = 255
# The original extension shares ``EXTENSION_MAX`` with the stored one.
ORIGINAL_FILENAME_MAX = 255

# Broad categories of a file, derived from its mime: what a consumer shows and filters by
# without knowing every concrete type. ``other`` takes whatever the catalog does not name.
FILE_TYPES = (
    "image",
    "document",
    "table",
    "presentation",
    "text",
    "archive",
    "video",
    "font",
    "key",
    "email",
    "other",
)
FILE_TYPE_OTHER = "other"

UNKNOWN_MIME = "application/octet-stream"

# A random code collides once in many lifetimes of a store; three tries turn that into an
# unnoticed repeat of the insert rather than a refusal.
CODE_ATTEMPTS = 3
# The cleanup prunes the folder a registration has just made only in a narrow window; one
# repeat already closes it, the third try is the margin.
PLACE_ATTEMPTS = 3

CHUNK_SIZE = 1024 * 1024
# ``filetype`` looks at most this far into a file to recognise its signature.
HEAD_SIZE = 8192
# Several owners can stand behind one stored file, so writing through its path would change
# the file for all of them; the bytes on disk are read-only.
FILE_MODE = 0o444

CLEANUP_AFTER_HOURS_DEFAULT = 48
CLEANUP_LIMIT_DEFAULT = 0
MAX_FILE_SIZE_MB_DEFAULT = 128

# The module's temporary files: a spooled stream in ``tmp`` is ``core_storage-<hex>.part``; a copy
# across file systems next to its target is ``.<CODE><ext>.<hex>.part``.
TEMP_PREFIX = "core_storage-"
TEMP_SUFFIX = ".part"
# A temporary file is written to as its bytes arrive and handed over at once, so one untouched for
# an hour belongs to a process that died midway; the cleanup removes it.
TEMP_STALE_SECONDS = 3600

# The reconciliation of the base with the disk leaves younger rows and bytes alone: a registration
# commits its row and moves the bytes in one ``replace`` right after, so a row without bytes or
# bytes without a row is legitimate for moments, never for an hour.
RECONCILE_GRACE_SECONDS = 3600
# Crash leftovers are a handful of files. Bytes without a row by the dozen mean the storage root
# of another base — a copy left on the original's root — and the scheduled run refuses to delete
# them: more than this many, or more than this share of the rows.
ORPHAN_AUTO_LIMIT_FILES = 10
ORPHAN_AUTO_LIMIT_SHARE = 0.10
RECONCILE_PAGE = 1000
# How many codes or paths of one kind a report names before it only counts.
REPORT_NAMED = 20

__all__ = [
    "CHUNK_SIZE",
    "CLEANUP_AFTER_HOURS_DEFAULT",
    "CLEANUP_LIMIT_DEFAULT",
    "CODE_ATTEMPTS",
    "CODE_LEN",
    "EXTENSION_MAX",
    "FILE_MODE",
    "FILE_TYPES",
    "FILE_TYPE_OTHER",
    "HEAD_SIZE",
    "MAX_FILE_SIZE_MB_DEFAULT",
    "MIME_MAX",
    "ORIGINAL_FILENAME_MAX",
    "OWNER_ID_MAX",
    "OWNER_KEY_MAX",
    "ORPHAN_AUTO_LIMIT_FILES",
    "ORPHAN_AUTO_LIMIT_SHARE",
    "OWNER_TYPE_MAX",
    "PLACE_ATTEMPTS",
    "RECONCILE_GRACE_SECONDS",
    "RECONCILE_PAGE",
    "REPORT_NAMED",
    "SHA256_LEN",
    "STORE_MAX",
    "TEMP_PREFIX",
    "TEMP_STALE_SECONDS",
    "TEMP_SUFFIX",
    "TYPE_MAX",
    "UNKNOWN_MIME",
]
