"""CRUD for ``CodexFile`` — which files a codex note holds, under which title, in which order.

The rows only: putting the bytes into the storage and releasing its owner is ``codex.files`` (the
service) and ``codex.file_owner``. Each function owns its session, except ``codex_files_take``,
which runs inside the transaction deleting the notes.

**The holder** is checked in the transaction that writes the row (``_require_note``) and read-only
before the service touches the storage (``codex_file_check``): a live note of a live codex, and
not a codex — the two share ``CODEX@``, and a codex code is refused by name rather than as "not
found". A soft-deleted codex keeps its notes' files as they are, so its notes take no change.

**Order** is the tasks' (``tasks/crud/file.py``): a new file goes below every file of the note,
the person reorders the whole list. Rows are written and deleted through the ORM, so the change
feed carries each row's note.
"""

from __future__ import annotations

from sqlalchemy import func, select

from src.core.database import session_scope, write_scope
from src.core.utils.text import control_character
from src.modules.codex.codes import tagged
from src.modules.codex.constants import (
    CODEX_CODE_PREFIX,
    FILE_CODE_PREFIX,
    FILE_DESCRIPTION_MAX,
    FILE_TITLE_MAX,
    SORT_DEFAULT,
    SORT_STEP,
)
from src.modules.codex.errors import (
    CODEX_DELETED,
    FILE_ALREADY_ATTACHED,
    FILE_CONTROL_CHARACTER,
    FILE_HOLDER_IS_CODEX,
    FILE_NOT_FOUND,
    NOTE_DELETED,
    NOTE_NOT_FOUND,
    CodexRuleError,
)
from src.modules.codex.models import Codex, CodexFile, CodexNote
from src.modules.codex.text import fit

_ORDER = (CodexFile.sort.desc(), CodexFile.created_at.asc(), CodexFile.file_code.asc())


def _file(code: str) -> str:
    return tagged(FILE_CODE_PREFIX, code) or ""


def _note(code: str) -> str:
    return tagged(CODEX_CODE_PREFIX, code) or ""


def _fields(title: str | None, description: str | None) -> tuple[str, str]:
    refuse_control_characters(title=title, description=description)
    return (
        fit(title, FILE_TITLE_MAX, "File title"),
        fit(description, FILE_DESCRIPTION_MAX, "File description"),
    )


def refuse_control_characters(*, title: str | None = None, description: str | None = None) -> None:
    """A file's title is one line, its description is prose (``src.core.utils.text``) — the rule
    of every surface, as a task's files have it (``tasks.crud.file``). The file's name is the
    storage's to refuse."""
    for field, value, prose in (
        ("title", title, False),
        ("description", description, True),
    ):
        control = control_character(value, prose=prose)
        if control is not None:
            raise CodexRuleError(
                FILE_CONTROL_CHARACTER,
                f"The file's {field} holds a control character ({control}) — remove it and send "
                "again",
                params={"field": field},
            )


async def _require_note(s, note_code: str) -> None:
    if await s.get(Codex, note_code) is not None:
        raise CodexRuleError(
            FILE_HOLDER_IS_CODEX,
            f"{_note(note_code)} is a codex, not a note — files are attached to the notes "
            "inside a codex.",
        )
    note = await s.get(CodexNote, note_code)
    if note is None:
        raise CodexRuleError(NOTE_NOT_FOUND, f"No codex note {_note(note_code)}.")
    if note.deleted_at is not None:
        raise CodexRuleError(
            NOTE_DELETED, f"{_note(note_code)} is deleted — a file goes to a live note only."
        )
    codex = await s.get(Codex, note.codex_code)
    if codex is None or codex.deleted_at is not None:
        raise CodexRuleError(
            CODEX_DELETED,
            f"The codex of {_note(note_code)} is deleted — its notes keep their files as they "
            "are until it is restored.",
        )


async def _require_absent(s, note_code: str, file_code: str) -> None:
    if await s.get(CodexFile, (note_code, file_code)) is not None:
        raise CodexRuleError(
            FILE_ALREADY_ATTACHED,
            f"{_file(file_code)} is in {_note(note_code)} already — a file is in a note once.",
            params={"file": _file(file_code)},
        )


async def _sort_at_end(s, note_code: str) -> int:
    """A position below every file of the note; the first one gets ``SORT_DEFAULT``."""
    stmt = select(func.min(CodexFile.sort)).where(CodexFile.note_code == note_code)
    lowest = (await s.execute(stmt)).scalar_one_or_none()
    return SORT_DEFAULT if lowest is None else lowest - SORT_STEP


async def codex_file_check(
    note_code: str,
    *,
    file_code: str | None = None,
    title: str | None = None,
    description: str | None = None,
) -> None:
    """Every refusal ``codex_file_create`` would give that is known before the file is stored."""
    _fields(title, description)
    async with session_scope() as s:
        await _require_note(s, note_code)
        if file_code is not None:
            await _require_absent(s, note_code, file_code)


async def codex_file_create(
    *,
    note_code: str,
    file_code: str,
    title: str | None = None,
    description: str | None = None,
) -> CodexFile:
    """Bind a stored file to a live note, at the end of its files. A refusal writes nothing."""
    title, description = _fields(title, description)
    async with write_scope() as s:
        await _require_note(s, note_code)
        await _require_absent(s, note_code, file_code)
        row = CodexFile(
            note_code=note_code,
            file_code=file_code,
            title=title,
            description=description,
            sort=await _sort_at_end(s, note_code),
        )
        s.add(row)
        await s.flush()
        await s.refresh(row)
    return row


async def codex_file_get(note_code: str, file_code: str) -> CodexFile | None:
    async with session_scope() as s:
        return await s.get(CodexFile, (note_code, file_code))


async def codex_file_list(note_code: str) -> list[CodexFile]:
    """The note's files top to bottom."""
    stmt = select(CodexFile).where(CodexFile.note_code == note_code).order_by(*_ORDER)
    async with session_scope() as s:
        return list((await s.execute(stmt)).scalars().all())


async def codex_file_list_by_file(file_code: str) -> list[CodexFile]:
    """Every note holding the file — where a ``FILE@`` code is bound."""
    stmt = (
        select(CodexFile)
        .where(CodexFile.file_code == file_code)
        .order_by(CodexFile.created_at.asc(), CodexFile.note_code.asc())
    )
    async with session_scope() as s:
        return list((await s.execute(stmt)).scalars().all())


async def codex_file_pairs() -> set[tuple[str, str]]:
    """``(note_code, file_code)`` of every binding row — the reconciliation's side of the pairs."""
    stmt = select(CodexFile.note_code, CodexFile.file_code)
    async with session_scope() as s:
        return {(note_code, file_code) for note_code, file_code in await s.execute(stmt)}


async def codex_file_update(
    note_code: str,
    file_code: str,
    *,
    title: str | None = None,
    description: str | None = None,
) -> CodexFile | None:
    """Change the given fields (``None`` = leave as is); ``None`` — the file is not in the note."""
    checked_title, checked_description = _fields(title, description)
    async with write_scope() as s:
        row = await s.get(CodexFile, (note_code, file_code))
        if row is None:
            return None
        if title is not None:
            row.title = checked_title
        if description is not None:
            row.description = checked_description
        await s.flush()
        await s.refresh(row)
    return row


async def codex_file_reorder(note_code: str, codes: list[str]) -> None:
    """Put the named files of a note in this order, top to bottom; the rest keep their order
    below. A code that is not this note's file is refused, and nothing moves."""
    wanted = list(dict.fromkeys(codes))
    async with write_scope() as s:
        stmt = select(CodexFile).where(CodexFile.note_code == note_code)
        rows = {row.file_code: row for row in (await s.execute(stmt)).scalars().all()}
        foreign = [code for code in wanted if code not in rows]
        if foreign:
            raise CodexRuleError(
                FILE_NOT_FOUND,
                f"Not files of {_note(note_code)}: {', '.join(_file(code) for code in foreign)}.",
            )
        top = SORT_DEFAULT + (len(wanted) - 1) * SORT_STEP
        for position, code in enumerate(wanted):
            rows[code].sort = top - position * SORT_STEP
        rest = sorted(
            (row for code, row in rows.items() if code not in wanted),
            key=lambda row: (-row.sort, row.created_at, row.file_code),
        )
        for position, row in enumerate(rest, start=len(wanted)):
            row.sort = top - position * SORT_STEP


async def codex_file_delete(note_code: str, file_code: str) -> bool:
    """Remove the binding row; ``True`` — the note held the file. The storage owner is the
    caller's to release (``codex.files.codex_file_detach``)."""
    async with write_scope() as s:
        row = await s.get(CodexFile, (note_code, file_code))
        if row is None:
            return False
        await s.delete(row)
    return True


async def codex_files_take(s, note_codes: list[str]) -> list[tuple[str, str]]:
    """Delete the binding rows of notes about to go for good, in their transaction; return
    ``(note_code, file_code)`` of each — the owners to release once it commits."""
    stmt = select(CodexFile).where(CodexFile.note_code.in_(note_codes))
    rows = list((await s.execute(stmt)).scalars().all())
    taken = [(row.note_code, row.file_code) for row in rows]
    for row in rows:
        await s.delete(row)
    await s.flush()
    return taken


__all__ = [
    "codex_file_check",
    "codex_file_create",
    "refuse_control_characters",
    "codex_file_delete",
    "codex_file_get",
    "codex_file_list",
    "codex_file_list_by_file",
    "codex_file_pairs",
    "codex_file_reorder",
    "codex_file_update",
    "codex_files_take",
]
