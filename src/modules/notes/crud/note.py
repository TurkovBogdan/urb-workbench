"""CRUD for ``Note`` — the service the consumers build on. Each function owns its own session,
except that ``note_create`` can join the consumer's.

Nothing here asks who the note is for: a consumer creates a note, keeps its code in a link table
of its own, and reads it back by that code. A note without any link is legitimate — the module
has no notion of an owner to miss.

Reads hide logically deleted rows unless ``include_deleted`` is passed: for the rest of the code
"deleted" means "does not exist".

Writes go through the ORM, not bulk ``update()``: the change feed (``core_changes``) takes its
events from the session's objects, and a bulk statement would reach a listener without the code.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Iterable
from contextlib import asynccontextmanager

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import defer

from src.core.database import session_scope, write_scope
from src.core.utils.date import utc_now
from src.modules.notes.codes import new_code
from src.modules.notes.constants import BODY_MAX, DESCRIPTION_MAX, TITLE_MAX
from src.modules.notes.models.note import Note
from src.modules.notes.text import fit


def _title(value: str) -> str:
    title = fit(value.strip(), TITLE_MAX, "Note title")
    if not title:
        raise ValueError("Note title is empty — a note is found by its title in every list.")
    return title


@asynccontextmanager
async def _writing(session: AsyncSession | None) -> AsyncIterator[AsyncSession]:
    """The caller's transaction when given, else one of our own."""
    if session is not None:
        yield session
        return
    async with write_scope() as s:
        yield s


async def note_create(
    *,
    title: str,
    description: str | None = None,
    body: str | None = None,
    session: AsyncSession | None = None,
) -> Note:
    """Create a note; over a limit or an empty title — ``ValueError``, and nothing is written.

    ``session`` — the consumer's open write transaction: the note and the consumer's link to it
    are then written together, and a refused link leaves no note behind.
    """
    row = Note(
        code=new_code(),
        title=_title(title),
        description=fit(description, DESCRIPTION_MAX, "Note description"),
        body=fit(body, BODY_MAX, "Note body"),
    )
    async with _writing(session) as s:
        s.add(row)
        await s.flush()
        await s.refresh(row)
    return row


async def note_get(code: str, *, include_deleted: bool = False) -> Note | None:
    """One note, whole."""
    stmt = select(Note).where(Note.code == code)
    if not include_deleted:
        stmt = stmt.where(Note.deleted_at.is_(None))
    async with session_scope() as s:
        return (await s.execute(stmt)).scalar_one_or_none()


async def note_get_many(codes: Iterable[str], *, include_deleted: bool = False) -> list[Note]:
    """Notes by codes, in the order the codes came, without ``body``.

    This is how a consumer draws its list of documents: the order is the consumer's (its link
    table holds the position), so it is kept as passed, and a code with no live row is skipped.
    The body stays unloaded and raises on access — a list that quietly pulled every 64K text
    would cost exactly what this function exists to avoid.
    """
    wanted = list(dict.fromkeys(codes))
    if not wanted:
        return []
    stmt = select(Note).where(Note.code.in_(wanted)).options(defer(Note.body, raiseload=True))
    if not include_deleted:
        stmt = stmt.where(Note.deleted_at.is_(None))
    async with session_scope() as s:
        found = {row.code: row for row in (await s.execute(stmt)).scalars().all()}
    return [found[code] for code in wanted if code in found]


async def note_update(
    code: str,
    *,
    title: str | None = None,
    description: str | None = None,
    body: str | None = None,
) -> Note | None:
    """Update the given fields (``None`` = leave alone, ``""`` = clear); ``body`` is whole.

    ``None`` — no such live note: a deleted one is not editable, ``note_restore`` first. Every
    value is checked before the row is touched, so a refusal leaves the note as it was.
    """
    values: dict[str, str] = {}
    if title is not None:
        values["title"] = _title(title)
    if description is not None:
        values["description"] = fit(description, DESCRIPTION_MAX, "Note description")
    if body is not None:
        values["body"] = fit(body, BODY_MAX, "Note body")
    async with write_scope() as s:
        row = await s.get(Note, code)
        if row is None or row.deleted_at is not None:
            return None
        for field, value in values.items():
            setattr(row, field, value)
        await s.flush()
        await s.refresh(row)
    return row


async def note_delete(code: str, *, hard: bool = False) -> bool:
    """Delete a note: softly (the default) or physically. ``True`` — the row existed.

    ``hard=True`` also removes the consumers' links to it, by the ``ON DELETE CASCADE`` they
    declare on their side — this module does not know who they are. A soft delete of an already
    deleted note keeps its first mark.
    """
    async with write_scope() as s:
        row = await s.get(Note, code)
        if row is None:
            return False
        if hard:
            await s.delete(row)
        elif row.deleted_at is None:
            row.deleted_at = utc_now()
    return True


async def note_restore(code: str) -> bool:
    """Clear the deletion mark. ``True`` — the note was deleted and has been brought back."""
    async with write_scope() as s:
        row = await s.get(Note, code)
        if row is None or row.deleted_at is None:
            return False
        row.deleted_at = None
    return True


__all__ = [
    "note_create",
    "note_delete",
    "note_get",
    "note_get_many",
    "note_restore",
    "note_update",
]
