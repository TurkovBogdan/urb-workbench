"""Refusal codes of the codex HTTP layer.

The interface looks the code ``codex.<entity>.<reason>`` up in its dictionary
(``web/src/features/codex/locales`` → ``codex.error.<entity>.<reason>``); the response text is the
English fallback. A broken tree rule carries no code: its text names the rule and the numbers,
and that is what the person needs to see.
"""

from __future__ import annotations

CODEX_NOT_FOUND = "codex.codex.not_found"
CODEX_DELETED = "codex.codex.deleted"
CODEX_NOT_DELETED = "codex.codex.not_deleted"
NOTE_NOT_FOUND = "codex.note.not_found"
NOTE_DELETED = "codex.note.deleted"
NOTE_NOT_DELETED = "codex.note.not_deleted"
NOTE_HAS_CHILDREN = "codex.note.has_children"
MOUNT_NOT_FOUND = "codex.mount.not_found"

__all__ = [
    "CODEX_DELETED",
    "CODEX_NOT_DELETED",
    "CODEX_NOT_FOUND",
    "MOUNT_NOT_FOUND",
    "NOTE_DELETED",
    "NOTE_HAS_CHILDREN",
    "NOTE_NOT_DELETED",
    "NOTE_NOT_FOUND",
]
