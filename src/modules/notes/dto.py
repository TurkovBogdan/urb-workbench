"""DTOs of the ``notes`` module — what the document page and the consumers' lists receive.

A code goes out as ``NOTE@…`` (``prefixed``: the type word only in JSON, ``model_dump()`` stays
bare). Dates are the core's ``DatetimeUTCStr`` — the SQL format the frontend parser expects.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from src.core.utils.date import DatetimeUTCStr
from src.modules.notes.codes import prefixed
from src.modules.notes.constants import NOTE_CODE_PREFIX

NoteCode = prefixed(NOTE_CODE_PREFIX)


class NoteSummaryRow(BaseModel):
    """A note in a consumer's list: everything but the text.

    ``deleted_at`` goes out so a list that shows deleted documents tells them apart by the data.
    """

    model_config = ConfigDict(from_attributes=True)

    code: NoteCode
    title: str
    description: str = ""
    created_at: DatetimeUTCStr
    updated_at: DatetimeUTCStr
    deleted_at: DatetimeUTCStr | None = None


class NoteRow(NoteSummaryRow):
    """A note whole — the document page."""

    body: str = ""


__all__ = ["NoteCode", "NoteRow", "NoteSummaryRow"]
