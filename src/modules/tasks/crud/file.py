"""CRUD for ``TasksFile`` — which files a task holds, under which title, in which order.

The rows only: putting the bytes into the storage and releasing its owner is ``tasks.files`` (the
service) and ``tasks.file_owner``. Each function owns its session, except ``task_files_take``,
which runs inside the transaction deleting the holder.

**Where a file was attached** is checked in the transaction that writes the row
(``_require_place``): the task is live, the note is a live note of this task, the stage is this
task's, and no more than one of the two is named. The FKs would take a note of another task
without a word. The same checks run read-only before the service touches the storage
(``task_file_check``), so a refusal that can be known up front writes nothing anywhere.

**Order** is the task notes' (``crud/note.py``): a new file goes below every file of the task, the
person reorders the whole list, and a title edit does not move a file.

Rows are deleted through the ORM, not with a bulk statement: the change feed then carries each
row's task, note and stage, and a screen recognises "this is about me" without re-reading.
"""

from __future__ import annotations

from sqlalchemy import func, select

from src.core.database import session_scope, write_scope
from src.core.utils.text import control_character
from src.modules.notes.models.note import Note
from src.modules.tasks.codes import tagged
from src.modules.tasks.constants import (
    FILE_CODE_PREFIX,
    FILE_DESCRIPTION_MAX,
    FILE_TITLE_MAX,
    NOTE_CODE_PREFIX,
    SORT_DEFAULT,
    SORT_STEP,
    STAGE_CODE_PREFIX,
    TASK_CODE_PREFIX,
)
from src.modules.tasks.errors import (
    FILE_ALREADY_ATTACHED,
    FILE_CONTROL_CHARACTER,
    FILE_FOREIGN_PLACE,
    FILE_NOT_FOUND,
    TASK_DELETED,
    TASK_NOT_FOUND,
    TaskRuleError,
)
from src.modules.tasks.models.file import TasksFile
from src.modules.tasks.models.note import TasksNote
from src.modules.tasks.models.stage import TasksStage
from src.modules.tasks.models.task import TasksTask
from src.modules.tasks.rules import task_accepts_edits
from src.modules.tasks.text import fit

_ORDER = (TasksFile.sort.desc(), TasksFile.created_at.asc(), TasksFile.file_code.asc())


def _file(code: str) -> str:
    return tagged(FILE_CODE_PREFIX, code) or ""


def _task(code: str) -> str:
    return tagged(TASK_CODE_PREFIX, code) or ""


def _fields(title: str | None, description: str | None) -> tuple[str, str]:
    refuse_control_characters(title=title, description=description)
    return (
        fit(title, FILE_TITLE_MAX, "File title"),
        fit(description, FILE_DESCRIPTION_MAX, "File description"),
    )


def refuse_control_characters(*, title: str | None = None, description: str | None = None) -> None:
    """A file's title is one line, its description is prose (``src.core.utils.text``): the rule
    of every surface, given here so the person's upload, the agent and an upload token meet the
    same refusal — ``FILE_CONTROL_CHARACTER`` with the field named. The file's name is the
    storage's to refuse (``core_storage.names.split_filename``)."""
    for field, value, prose in (
        ("title", title, False),
        ("description", description, True),
    ):
        control = control_character(value, prose=prose)
        if control is not None:
            raise TaskRuleError(
                FILE_CONTROL_CHARACTER,
                f"The file's {field} holds a control character ({control}) — remove it and send "
                "again",
                params={"field": field},
            )


async def _require_place(
    s, task_code: str, note_code: str | None, stage_code: str | None
) -> None:
    task = await s.get(TasksTask, task_code)
    if task is None:
        raise TaskRuleError(TASK_NOT_FOUND, f"Task {_task(task_code)} does not exist.")
    if not task_accepts_edits(task):
        raise TaskRuleError(
            TASK_DELETED,
            f"Task {_task(task_code)} is deleted — a file goes to a live task only.",
        )
    if note_code and stage_code:
        raise TaskRuleError(
            FILE_FOREIGN_PLACE,
            "A file is attached to the task, to one of its notes or to one of its stages — "
            "name a note or a stage, not both.",
        )
    if note_code:
        link = await s.get(TasksNote, note_code)
        note = await s.get(Note, note_code)
        if link is None or link.task_code != task_code or note is None or note.deleted_at:
            raise TaskRuleError(
                FILE_FOREIGN_PLACE,
                f"{tagged(NOTE_CODE_PREFIX, note_code)} is not a live note of {_task(task_code)}.",
            )
    if stage_code:
        stage = await s.get(TasksStage, stage_code)
        if stage is None or stage.task_code != task_code:
            raise TaskRuleError(
                FILE_FOREIGN_PLACE,
                f"{tagged(STAGE_CODE_PREFIX, stage_code)} is not a stage of {_task(task_code)}.",
            )


async def _require_absent(s, task_code: str, file_code: str) -> None:
    if await s.get(TasksFile, (task_code, file_code)) is not None:
        raise TaskRuleError(
            FILE_ALREADY_ATTACHED,
            f"{_file(file_code)} is in {_task(task_code)} already — a file is in a task once, "
            "and its code serves the whole task.",
            params={"file": _file(file_code)},
        )


async def _sort_at_end(s, task_code: str) -> int:
    """A position below every file of the task; the first one gets ``SORT_DEFAULT``."""
    stmt = select(func.min(TasksFile.sort)).where(TasksFile.task_code == task_code)
    lowest = (await s.execute(stmt)).scalar_one_or_none()
    return SORT_DEFAULT if lowest is None else lowest - SORT_STEP


async def task_file_check(
    task_code: str,
    *,
    file_code: str | None = None,
    note_code: str | None = None,
    stage_code: str | None = None,
    title: str | None = None,
    description: str | None = None,
) -> None:
    """Every refusal ``task_file_create`` would give that is known before the file is stored.

    ``file_code`` — a file already stored, attached by its code: whether the task holds it is
    known up front too.
    """
    _fields(title, description)
    async with session_scope() as s:
        await _require_place(s, task_code, note_code, stage_code)
        if file_code is not None:
            await _require_absent(s, task_code, file_code)


async def task_file_create(
    *,
    task_code: str,
    file_code: str,
    note_code: str | None = None,
    stage_code: str | None = None,
    title: str | None = None,
    description: str | None = None,
) -> TasksFile:
    """Bind a stored file to a live task, at the end of its files. A refusal writes nothing."""
    title, description = _fields(title, description)
    async with write_scope() as s:
        await _require_place(s, task_code, note_code, stage_code)
        await _require_absent(s, task_code, file_code)
        row = TasksFile(
            task_code=task_code,
            file_code=file_code,
            note_code=note_code or None,
            stage_code=stage_code or None,
            title=title,
            description=description,
            sort=await _sort_at_end(s, task_code),
        )
        s.add(row)
        await s.flush()
        await s.refresh(row)
    return row


async def task_file_get(task_code: str, file_code: str) -> TasksFile | None:
    async with session_scope() as s:
        return await s.get(TasksFile, (task_code, file_code))


async def task_file_list(task_code: str) -> list[TasksFile]:
    """The task's files top to bottom — those attached to its notes and stages included."""
    stmt = select(TasksFile).where(TasksFile.task_code == task_code).order_by(*_ORDER)
    async with session_scope() as s:
        return list((await s.execute(stmt)).scalars().all())


async def task_file_list_by_file(file_code: str) -> list[TasksFile]:
    """Every task holding the file — where a ``FILE@`` code is bound."""
    stmt = (
        select(TasksFile)
        .where(TasksFile.file_code == file_code)
        .order_by(TasksFile.created_at.asc(), TasksFile.task_code.asc())
    )
    async with session_scope() as s:
        return list((await s.execute(stmt)).scalars().all())


async def task_file_pairs() -> set[tuple[str, str]]:
    """``(task_code, file_code)`` of every binding row — the reconciliation's side of the pairs."""
    stmt = select(TasksFile.task_code, TasksFile.file_code)
    async with session_scope() as s:
        return {(task_code, file_code) for task_code, file_code in await s.execute(stmt)}


async def task_file_update(
    task_code: str,
    file_code: str,
    *,
    title: str | None = None,
    description: str | None = None,
) -> TasksFile | None:
    """Change the given fields (``None`` = leave as is); ``None`` — the file is not in the task."""
    checked_title, checked_description = _fields(title, description)
    async with write_scope() as s:
        row = await s.get(TasksFile, (task_code, file_code))
        if row is None:
            return None
        if title is not None:
            row.title = checked_title
        if description is not None:
            row.description = checked_description
        await s.flush()
        await s.refresh(row)
    return row


async def task_file_reorder(task_code: str, codes: list[str]) -> None:
    """Put the named files of a task in this order, top to bottom.

    The order comes whole, as the person left it after a drag. Files left out keep their order
    below the named ones. A code that is not this task's file is refused, and nothing moves.
    """
    wanted = list(dict.fromkeys(codes))
    async with write_scope() as s:
        stmt = select(TasksFile).where(TasksFile.task_code == task_code)
        rows = {row.file_code: row for row in (await s.execute(stmt)).scalars().all()}
        foreign = [code for code in wanted if code not in rows]
        if foreign:
            raise TaskRuleError(
                FILE_NOT_FOUND,
                f"Not files of {_task(task_code)}: {', '.join(_file(code) for code in foreign)}.",
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


async def task_file_delete(task_code: str, file_code: str) -> bool:
    """Remove the binding row; ``True`` — the task held the file. The storage owner is the
    caller's to release (``tasks.files.task_file_detach``)."""
    async with write_scope() as s:
        row = await s.get(TasksFile, (task_code, file_code))
        if row is None:
            return False
        await s.delete(row)
    return True


async def task_files_take(
    s,
    *,
    task_codes: list[str] | None = None,
    note_code: str | None = None,
    stage_code: str | None = None,
) -> list[tuple[str, str]]:
    """Delete the binding rows of a holder about to go, in its own transaction; return
    ``(task_code, file_code)`` of each — the owners to release once that transaction commits.

    The holder: whole tasks (``task_codes``), or one note, or one stage.
    """
    stmt = select(TasksFile)
    if task_codes is not None:
        stmt = stmt.where(TasksFile.task_code.in_(task_codes))
    elif note_code is not None:
        stmt = stmt.where(TasksFile.note_code == note_code)
    elif stage_code is not None:
        stmt = stmt.where(TasksFile.stage_code == stage_code)
    else:
        raise ValueError("Name the holder whose files go: task_codes, note_code or stage_code.")
    rows = list((await s.execute(stmt)).scalars().all())
    taken = [(row.task_code, row.file_code) for row in rows]
    for row in rows:
        await s.delete(row)
    await s.flush()
    return taken


__all__ = [
    "refuse_control_characters",
    "task_file_check",
    "task_file_create",
    "task_file_delete",
    "task_file_get",
    "task_file_list",
    "task_file_list_by_file",
    "task_file_pairs",
    "task_file_reorder",
    "task_file_update",
    "task_files_take",
]
