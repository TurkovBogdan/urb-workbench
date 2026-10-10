"""When a note may be edited, and how long its text may grow — one answer for every surface.

The rule belongs to the document, not to whoever writes it: the document page (``api.py``), a
task page and the agent (the ``workbench`` module) reach the same row. The refusal's wording is
each surface's own; whether to refuse is decided here.
"""

from __future__ import annotations

from src.modules.notes.constants import BODY_MAX
from src.modules.notes.models.note import Note

NOTE_BODY_LIMIT = BODY_MAX


def note_accepts_edits(note: Note) -> bool:
    """A note in the bin takes no edits — a person restores it first."""
    return note.deleted_at is None


__all__ = ["NOTE_BODY_LIMIT", "note_accepts_edits"]
