"""CRUD for ``TasksNote`` — the work journal. Each function owns its session.

Entries are never deleted by the agent and never re-titled, and this layer has no entry edit at
all; the one editable part is the body, which only the MCP content handler writes
(``mcp/content/note.py``). ``note_resolve`` fills the resolution **once**. A repeat call on an already resolved entry is
refused — otherwise history could be rewritten to fit the outcome, and analysing a failure would
stop meaning anything. A reversal is recorded as a new entry, not as an edit of the old one.

Who writes which half of a row is not this layer's call: that is the surface (MCP/HTTP) — the agent
simply has no tool to create a ``remark`` and no endpoint to fill in an answer where the person
answers.

An open entry is one with an empty ``resolution``. A ``fact`` is resolved at creation, so it never
counts as open: it is waiting for nothing.
"""

from __future__ import annotations

from sqlalchemy import delete as sa_delete, func, select

from src.core.database import session_scope, write_scope
from src.modules.core_changes import DELETED, mark_changes
from src.modules.tasks.codes import new_code
from src.modules.tasks.constants import (
    NOTE_BODY_MAX,
    NOTE_TYPES,
    NOTE_TYPES_OPENABLE,
    RESOLUTION_MAX,
    TASK_TYPES_WITH_PLAN,
    TITLE_MAX,
)
from src.modules.tasks.errors import NOTE_ALREADY_RESOLVED, TaskRuleError
from src.modules.tasks.models.note import TasksNote
from src.modules.tasks.models.stage import TasksStage
from src.modules.tasks.models.task import TasksTask
from src.modules.tasks.text import clip


async def _require_planned_task(s, task_code: str) -> None:
    """A live task WITH A PLAN, or refuse — the same two checks as for a stage.

    The journal starts at ``standard`` for the same reason stages do: ``simple`` has none in its
    workflow or in the UI, so an entry written there would never be shown to anyone.
    """
    stmt = select(TasksTask.type).where(
        TasksTask.code == task_code, TasksTask.deleted_at.is_(None)
    )
    task_type = (await s.execute(stmt)).scalar_one_or_none()
    if task_type is None:
        raise ValueError(
            f"Task {task_code!r} does not exist (or is deleted) — "
            "a journal entry always belongs to a live task."
        )
    if task_type not in TASK_TYPES_WITH_PLAN:
        raise ValueError(
            f"Task {task_code!r} is {task_type!r} and keeps no journal — it starts at "
            f"{' / '.join(TASK_TYPES_WITH_PLAN)}. Raise its type first, then write the entry."
        )


async def _require_stage_of(s, stage_code: str, task_code: str) -> None:
    """The stage exists and belongs to the same task as the entry."""
    stmt = select(TasksStage.task_code).where(TasksStage.code == stage_code)
    owner = (await s.execute(stmt)).scalar_one_or_none()
    if owner is None:
        raise ValueError(f"Stage {stage_code!r} does not exist.")
    if owner != task_code:
        raise ValueError(
            f"Stage {stage_code!r} belongs to task {owner!r}, but the entry belongs to "
            f"{task_code!r} — an entry never points at another task's stage."
        )


async def note_create(
    *,
    task_code: str,
    type: str,
    title: str,
    body: str | None = None,
    stage_code: str | None = None,
    resolution: str | None = None,
) -> TasksNote:
    """Create a journal entry.

    ``resolution`` at creation makes sense only for ``fact``: a fact is resolved the moment it is
    written and has nothing to wait for. The other types start open and are closed by
    ``note_resolve``.
    """
    if type not in NOTE_TYPES:
        raise ValueError(
            f"Unknown note type {type!r}; expected one of {', '.join(NOTE_TYPES)}."
        )
    async with write_scope() as s:
        await _require_planned_task(s, task_code)
        if stage_code:
            await _require_stage_of(s, stage_code, task_code)
        row = TasksNote(
            code=new_code(),
            task_code=task_code,
            stage_code=stage_code or None,
            type=type,
            title=clip(title, TITLE_MAX),
            body=clip(body, NOTE_BODY_MAX),
            resolution=clip(resolution, RESOLUTION_MAX),
        )
        s.add(row)
        await s.flush()
        await s.refresh(row)
    return row


async def note_get(code: str) -> TasksNote | None:
    async with session_scope() as s:
        return await s.get(TasksNote, code)


async def note_list_by_task(
    task_code: str, *, type: str | None = None, open_only: bool = False
) -> list[TasksNote]:
    """The task's journal in order of appearance; can be narrowed to one type or to open entries."""
    stmt = (
        select(TasksNote)
        .where(TasksNote.task_code == task_code)
        .order_by(TasksNote.created_at.asc(), TasksNote.code.asc())
    )
    if type is not None:
        stmt = stmt.where(TasksNote.type == type)
    if open_only:
        stmt = stmt.where(TasksNote.resolution == "")
    async with session_scope() as s:
        return list((await s.execute(stmt)).scalars().all())


async def note_resolve(code: str, resolution: str) -> TasksNote | None:
    """Resolve an entry. ``None`` — no such entry; already resolved — ``TaskRuleError``.

    Whitespace is stripped BEFORE the emptiness check: otherwise a whitespace-only string would
    close the entry while leaving it blank to the eye — open in meaning, but closed to the gate.
    """
    text = clip(resolution.strip(), RESOLUTION_MAX)
    if not text:
        raise ValueError("Resolution cannot be empty — an entry is closed by what was decided.")
    async with write_scope() as s:
        row = await s.get(TasksNote, code)
        if row is None:
            return None
        if row.resolution:
            raise TaskRuleError(
                NOTE_ALREADY_RESOLVED,
                f"Entry {code!r} is already resolved — record a new entry instead of "
                "rewriting this one; the journal is append-only.",
            )
        row.resolution = text
        await s.flush()
        await s.refresh(row)
    return row


async def note_delete(code: str) -> bool:
    """Hard-delete an entry. Not exposed to the agent — cleaning the journal is the person's job."""
    async with write_scope() as s:
        row = await s.get(TasksNote, code)
        if row is None:
            return False
        await s.execute(sa_delete(TasksNote).where(TasksNote.code == code))
        # A bulk statement yields no objects — so we name the code to the change feed ourselves.
        mark_changes(s, "tasks.note", DELETED, [code])
    return True


async def note_open_count_by_task_codes(
    task_codes: list[str], *, types: tuple[str, ...] = NOTE_TYPES_OPENABLE
) -> dict[str, int]:
    """``task_code → number of open entries`` of the given types.

    ``fact`` is not in ``NOTE_TYPES_OPENABLE`` at all: it is resolved the moment it is written and
    waits for nothing. The other three do wait, but for **different** things — hence the parameter.

    For display to the person, everything open is counted. For the **hand-off gate** — only
    ``NOTE_TYPES_BLOCKING`` (decision and remark): those are within the power of whoever hands the
    work in to close. A finding is not addressed here — the person triages it in their own order,
    and were we to count it equally, the very first finding would lock the hand-off forever,
    because the executor has no way to clear it.
    """
    if not task_codes:
        return {}
    stmt = (
        select(TasksNote.task_code, func.count())
        .where(
            TasksNote.task_code.in_(task_codes),
            TasksNote.resolution == "",
            TasksNote.type.in_(types),
        )
        .group_by(TasksNote.task_code)
    )
    async with session_scope() as s:
        return {code: count for code, count in (await s.execute(stmt)).all()}


__all__ = [
    "note_create",
    "note_delete",
    "note_get",
    "note_list_by_task",
    "note_open_count_by_task_codes",
    "note_resolve",
]
