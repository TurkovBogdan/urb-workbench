"""Refusal codes of the codex HTTP layer and of the codex file service.

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
FILE_NOT_FOUND = "codex.file.not_found"
"""The file is not in this note."""
FILE_ALREADY_ATTACHED = "codex.file.already_attached"
"""The file is in the note already — a file is in a note once."""
FILE_HOLDER_IS_CODEX = "codex.file.holder_is_codex"
"""A ``CODEX@`` code of a codex, not of a note: files are attached to notes only."""
FILE_NOT_STORED = "codex.file.not_stored"
"""No file under this code in the storage."""
FILE_FOREIGN_STORE = "codex.file.foreign_store"
"""The stored file lies in a store other than the one codex files are served from."""
FILE_CONTROL_CHARACTER = "codex.file.control_character"
"""A file's title or description holds a control character (``params.field`` names which)."""


class CodexRuleError(ValueError):
    """A refusal with a machine-readable name, for the surfaces to translate.

    A ``ValueError`` like every other refusal of the module, so a handler catching those catches
    this one too; the code rides next to the English text, and ``params`` — what the surface needs
    to word it or act on it (the file a note holds already).
    """

    def __init__(self, code: str, message: str, *, params: dict[str, str | int] | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.params = params or {}


__all__ = [
    "CODEX_DELETED",
    "CODEX_NOT_DELETED",
    "CODEX_NOT_FOUND",
    "CodexRuleError",
    "FILE_ALREADY_ATTACHED",
    "FILE_CONTROL_CHARACTER",
    "FILE_FOREIGN_STORE",
    "FILE_HOLDER_IS_CODEX",
    "FILE_NOT_FOUND",
    "FILE_NOT_STORED",
    "MOUNT_NOT_FOUND",
    "NOTE_DELETED",
    "NOTE_HAS_CHILDREN",
    "NOTE_NOT_DELETED",
    "NOTE_NOT_FOUND",
]
