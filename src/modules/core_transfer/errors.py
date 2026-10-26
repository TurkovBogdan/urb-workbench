"""Refusals of a transfer, each with a code the interface words in the person's language.

An archive comes from outside, so every refusal names its cause: a broken zip, another format,
an archive newer than the application. The codes have no module segment on purpose — the same
refusal reads the same for a task and for a codex, and its words live once, in the shared
dictionary (``common.errors.<code>``). The message stays English, for logs.
"""

from __future__ import annotations

NOT_ARCHIVE = "transfer_not_archive"
"""Not a zip, or a zip whose first entry is not this format's ``mimetype``."""
FOREIGN_FORMAT = "transfer_foreign_format"
"""An archive of another kind — a codex dropped where a task is awaited."""
NEWER_FORMAT = "transfer_newer_format"
"""Made by a newer version of the format (``params.version``, ``params.supported``)."""
MANIFEST_INVALID = "transfer_manifest_invalid"
ENTRY_NOT_ALLOWED = "transfer_entry_not_allowed"
"""An entry this format never writes (``params.name``)."""
INVENTORY_MISMATCH = "transfer_inventory_mismatch"
"""The entries differ from the manifest's list (``params.missing``, ``params.extra``)."""
ENTRY_DAMAGED = "transfer_entry_damaged"
"""An entry's size or sha256 differs from the manifest's (``params.name``)."""
ARCHIVE_TOO_LARGE = "transfer_archive_too_large"
"""Over an unpacking limit, or the upload over its own (``params.limit_mb``)."""
ARCHIVE_INCONSISTENT = "transfer_archive_inconsistent"
"""A row points at something the archive does not hold, or breaks a rule of its kind
(``params.detail``)."""
FILE_TOO_LARGE = "transfer_file_too_large"
"""A file of the archive is over this installation's storage ceiling (``params.name``,
``params.limit_mb``)."""
UPLOAD_NOT_FOUND = "transfer_upload_not_found"
PLAN_CHANGED = "transfer_plan_changed"
"""The base changed while the person was choosing: the conflicts are not the ones they saw."""
DECISION_INVALID = "transfer_decision_invalid"
"""A conflict without a choice, or a choice the conflict does not offer (``params.id``)."""
DEPTH_EXCEEDED = "transfer_depth_exceeded"
"""The chosen mix of «update» and «replace» would push a record here past the tree's levels
(``params.record``, ``params.levels``) — another choice is needed, the archive itself is fine."""


class TransferError(ValueError):
    """A transfer refusal with its code and the values its words need."""

    def __init__(self, code: str, message: str, *, params: dict[str, str | int] | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.params = params or {}


__all__ = [
    "ARCHIVE_INCONSISTENT",
    "ARCHIVE_TOO_LARGE",
    "DECISION_INVALID",
    "DEPTH_EXCEEDED",
    "ENTRY_DAMAGED",
    "ENTRY_NOT_ALLOWED",
    "FILE_TOO_LARGE",
    "FOREIGN_FORMAT",
    "INVENTORY_MISMATCH",
    "MANIFEST_INVALID",
    "NEWER_FORMAT",
    "NOT_ARCHIVE",
    "PLAN_CHANGED",
    "TransferError",
    "UPLOAD_NOT_FOUND",
]
