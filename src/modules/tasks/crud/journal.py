"""CRUD for ``TasksJournal`` — the work journal. Each function owns its session.

Entries are never deleted by the agent and never re-titled, and this layer has no entry edit at
all; the one editable part is the body, which only the MCP content handler writes
(``mcp/content/journal.py``). ``journal_resolve`` fills the resolution **once**. A repeat call on
an already resolved entry is refused — otherwise history could be rewritten to fit the outcome, and analysing a failure would
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
    JOURNAL_BODY_MAX,
    JOURNAL_TYPES,
    JOURNAL_TYPES_OPENABLE,
    RESOLUTION_MAX,
    TASK_TYPES_WITH_PLAN,
    TITLE_MAX,
)
from src.modules.tasks.errors import JOURNAL_ALREADY_RESOLVED, TaskRuleError
from src.modules.tasks.models.journal import TasksJournal
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


async def journal_create(
    *,
    task_code: str,
    type: str,
    title: str,
    body: str | None = None,
    stage_code: str | None = None,
    resolution: str | None = None,
) -> TasksJournal:
    """Create a journal entry.

    ``resolution`` at creation makes sense only for ``fact``: a fact is resolved the moment it is
    written and has nothing to wait for. The other types start open and are closed by
    ``journal_resolve``.
    """
    if type not in JOURNAL_TYPES:
        raise ValueError(
            f"Unknown journal entry type {type!r}; expected one of {', '.join(JOURNAL_TYPES)}."
        )
    async with write_scope() as s:
        await _require_planned_task(s, task_code)
        if stage_code:
            await _require_stage_of(s, stage_code, task_code)
        row = TasksJournal(
            code=new_code(),
            task_code=task_code,
            stage_code=stage_code or None,
            type=type,
            title=clip(title, TITLE_MAX),
            body=clip(body, JOURNAL_BODY_MAX),
            resolution=clip(resolution, RESOLUTION_MAX),
        )
        s.add(row)
        await s.flush()
        await s.refresh(row)
    return row


async def journal_get(code: str) -> TasksJournal | None:
    async with session_scope() as s:
        return await s.get(TasksJournal, code)


async def journal_list_by_task(
    task_code: str, *, type: str | None = None, open_only: bool = False
) -> list[TasksJournal]:
    """The task's journal in order of appearance; can be narrowed to one type or to open entries."""
    stmt = (
        select(TasksJournal)
        .where(TasksJournal.task_code == task_code)
        .order_by(TasksJournal.created_at.asc(), TasksJournal.code.asc())
    )
    if type is not None:
        stmt = stmt.where(TasksJournal.type == type)
    if open_only:
        stmt = stmt.where(TasksJournal.resolution == "")
    async with session_scope() as s:
        return list((await s.execute(stmt)).scalars().all())


async def journal_resolve(code: str, resolution: str) -> TasksJournal | None:
    """Resolve an entry. ``None`` — no such entry; already resolved — ``TaskRuleError``.

    Whitespace is stripped BEFORE the emptiness check: otherwise a whitespace-only string would
    close the entry while leaving it blank to the eye — open in meaning, but closed to the gate.
    """
    text = clip(resolution.strip(), RESOLUTION_MAX)
    if not text:
        raise ValueError("Resolution cannot be empty — an entry is closed by what was decided.")
    async with write_scope() as s:
        row = await s.get(TasksJournal, code)
        if row is None:
            return None
        if row.resolution:
            raise TaskRuleError(
                JOURNAL_ALREADY_RESOLVED,
                f"Entry {code!r} is already resolved, and a resolution is written once — "
                "record a new entry instead of rewriting this one.",
            )
        row.resolution = text
        await s.flush()
        await s.refresh(row)
    return row


async def journal_delete(code: str) -> bool:
    """Hard-delete an entry. Not exposed to the agent — cleaning the journal is the person's job."""
    async with write_scope() as s:
        row = await s.get(TasksJournal, code)
        if row is None:
            return False
        await s.execute(sa_delete(TasksJournal).where(TasksJournal.code == code))
        # A bulk statement yields no objects — so we name the code to the change feed ourselves.
        mark_changes(s, "tasks.journal", DELETED, [code])
    return True


async def journal_open_count_by_task_codes(
    task_codes: list[str], *, types: tuple[str, ...] = JOURNAL_TYPES_OPENABLE
) -> dict[str, int]:
    """``task_code → number of open entries`` of the given types.

    ``fact`` is not in ``JOURNAL_TYPES_OPENABLE`` at all: it is resolved the moment it is written and
    waits for nothing. The other three do wait, but for **different** things — hence the parameter.

    For display to the person, everything open is counted. For the **hand-off count** — only
    ``JOURNAL_TYPES_BLOCKING`` (decision and remark): those are the executor's to settle. A finding
    is not counted here — it is addressed to the person, who triages it in their own order. The
    count is reported, not enforced: the hand-off itself is never refused for it.
    """
    if not task_codes:
        return {}
    stmt = (
        select(TasksJournal.task_code, func.count())
        .where(
            TasksJournal.task_code.in_(task_codes),
            TasksJournal.resolution == "",
            TasksJournal.type.in_(types),
        )
        .group_by(TasksJournal.task_code)
    )
    async with session_scope() as s:
        return {code: count for code, count in (await s.execute(stmt)).all()}


__all__ = [
    "journal_create",
    "journal_delete",
    "journal_get",
    "journal_list_by_task",
    "journal_open_count_by_task_codes",
    "journal_resolve",
]
