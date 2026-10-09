"""HTTP API of the ``notes`` module (mounted at ``/internal/notes`` — see ``module.py``).

The document page only: read a note and save it. Creating, listing and deleting belong to the
consumers — a task adds a document to itself, a knowledge base places one in its tree — because
only they know where the note is going; this module would create it into nowhere.

**A code is accepted in both forms** — ``NOTE@<hash>`` and the bare hash, in any case. A foreign
prefix is a mixed-up argument and answers 400, not a 404 that would send the reader looking for a
deleted note.

**An unknown field in the body is a refusal, not silence** (``extra="forbid"``): a typo in a field
name would otherwise save the note without that value and answer 200.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter
from pydantic import BaseModel, ConfigDict, StringConstraints

from src.core.api import ApiError
from src.modules.notes.codes import bare_code
from src.modules.notes.constants import BODY_MAX, DESCRIPTION_MAX, NOTE_CODE_PREFIX, TITLE_MAX
from src.modules.notes.crud import note as note_crud
from src.modules.notes.dto import NoteRow
from src.modules.notes.errors import NOTE_DELETED, NOTE_NOT_FOUND
from src.modules.notes.models.note import Note

router = APIRouter()


class NoteBody(BaseModel):
    """The whole document as the page saves it: every field, an empty value erases its own.

    Surrounding whitespace in the title is stripped before the length check, so a title of only
    spaces is refused like an empty one. The body is kept as typed — whitespace in markdown is
    content.
    """

    model_config = ConfigDict(extra="forbid")

    title: Annotated[
        str, StringConstraints(strip_whitespace=True, min_length=1, max_length=TITLE_MAX)
    ]
    description: Annotated[
        str, StringConstraints(strip_whitespace=True, max_length=DESCRIPTION_MAX)
    ] = ""
    body: Annotated[str, StringConstraints(max_length=BODY_MAX)] = ""


def _code(value: str) -> str:
    try:
        return bare_code(value, NOTE_CODE_PREFIX) or ""
    except ValueError as error:
        raise ApiError.bad_request(str(error)) from error


async def _require(code: str) -> Note:
    """A note in any state, or 404: the page shows a deleted one as deleted, not as missing."""
    row = await note_crud.note_get(code, include_deleted=True)
    if row is None:
        raise ApiError.not_found("Note not found", code=NOTE_NOT_FOUND)
    return row


@router.get("/{code}")
async def get_note(code: str) -> NoteRow:
    """One note whole — including a deleted one: its state shows in ``deleted_at``."""
    return NoteRow.model_validate(await _require(_code(code)))


@router.put("/{code}")
async def update_note(code: str, payload: NoteBody) -> NoteRow:
    """Save the whole document. A deleted one is not editable — 409: it exists, but not for this."""
    bare = _code(code)
    existing = await _require(bare)
    if existing.deleted_at is not None:
        raise ApiError.conflict("Note is deleted — restore it first", code=NOTE_DELETED)
    row = await note_crud.note_update(
        bare, title=payload.title, description=payload.description, body=payload.body
    )
    if row is None:
        raise ApiError.not_found("Note not found", code=NOTE_NOT_FOUND)
    return NoteRow.model_validate(row)


__all__ = ["router"]
