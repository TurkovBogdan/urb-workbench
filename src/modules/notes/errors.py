"""Refusal codes of the notes HTTP layer.

The interface looks the code ``notes.<entity>.<reason>`` up in its dictionary
(``notes.error.<entity>.<reason>``); the response text is the English fallback.
"""

from __future__ import annotations

NOTE_NOT_FOUND = "notes.note.not_found"
NOTE_DELETED = "notes.note.deleted"

__all__ = ["NOTE_DELETED", "NOTE_NOT_FOUND"]
