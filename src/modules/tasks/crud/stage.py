"""CRUD for ``TasksStage`` — plan stages. Each function owns its session.

Two rules live here rather than in the schema, because both look at several values of a row at
once and at its siblings:

- **default number** — the task's maximum plus one. Computed in the same transaction as the
  insert: otherwise two stages created back to back would get the same number and hit the unique
  index;
- **closing requires evidence** — a move to ``done`` with empty ``evidence`` is refused. This is
  the only place where a status change checks anything, and it is the reason
  ``stage_update_status`` exists separately from the general update.

The system sets ``finished_at`` on entering a terminal status and ``started_at`` on first entering
``in_progress``. Both marks are facts, and a repeated transition does not overwrite them.
"""

from __future__ import annotations

from sqlalchemy import delete as sa_delete, func, select

from src.core.database import session_scope, write_scope
from src.core.utils.date import utc_now
from src.modules.core_changes import DELETED, mark_changes
from src.modules.tasks.codes import new_code
from src.modules.tasks.constants import (
    BODY_MAX,
    DESCRIPTION_MAX,
    EVIDENCE_MAX,
    STAGE_STATUS_DEFAULT,
    STATUS_CANCELED,
    STATUS_DONE,
    STATUS_IN_PROGRESS,
    TASK_STATUSES,
    TASK_STATUSES_TERMINAL,
    TASK_TYPES_WITH_STAGES,
    TITLE_MAX,
)
from src.modules.tasks.errors import STAGE_EVIDENCE_REQUIRED, TaskRuleError
from src.modules.tasks.models.stage import TasksStage
from src.modules.tasks.models.task import TasksTask
from src.modules.tasks.text import clip, fit


def _checked(value: str, allowed: tuple[str, ...], what: str) -> str:
    """A value from the vocabulary, or ``ValueError`` listing the allowed ones."""
    if value not in allowed:
        raise ValueError(f"Unknown {what} {value!r}; expected one of {', '.join(allowed)}.")
    return value


async def _require_staged_task(s, task_code: str) -> None:
    """A live task WITH STAGES, or refuse.

    Two checks, not one. A deleted task takes no stages — that much is obvious. The type is checked
    because stages exist **only on an extended task**: that is exactly the line between it and a
    standard one. A standard task keeps its plan as prose in ``plan``, and a stage silently created
    there would show up nowhere — the UI draws the stage board only for an extended task, so the
    row would stay invisible to both sides.
    """
    stmt = select(TasksTask.type).where(
        TasksTask.code == task_code, TasksTask.deleted_at.is_(None)
    )
    task_type = (await s.execute(stmt)).scalar_one_or_none()
    if task_type is None:
        raise ValueError(
            f"Task {task_code!r} does not exist (or is deleted) — "
            "a stage always belongs to a live task."
        )
    if task_type not in TASK_TYPES_WITH_STAGES:
        raise ValueError(
            f"Task {task_code!r} is {task_type!r}, and stages belong to "
            f"{' / '.join(TASK_TYPES_WITH_STAGES)} only — a {task_type!r} task carries its plan "
            "as prose in `plan`. Either write it there, or raise the type first if the work "
            "really needs steps with their own evidence."
        )


async def _next_number(s, task_code: str) -> int:
    """The task's highest stage number plus one; the first stage gets 1."""
    stmt = select(func.max(TasksStage.number)).where(TasksStage.task_code == task_code)
    return ((await s.execute(stmt)).scalar_one_or_none() or 0) + 1


async def _free_number(s, task_code: str, number: int, *, moving: str | None = None) -> int:
    """A number free in this task — or a refusal naming whoever holds it.

    Without this check a taken number hits the unique index and returns an ``IntegrityError``
    with a chunk of SQL: noise for the person, and for the agent a text it can neither understand
    nor act on. Reworking a plan (merge two stages, insert a third) is the most ordinary move, and
    it is the first place this surfaces.

    The tail is deliberately NOT renumbered here: the agent refers to "the third stage" in prose in
    the journal, and a silent shift would make such references false. Gaps in numbering are legal —
    the number orders, it does not count.
    """
    stmt = select(TasksStage.code, TasksStage.title).where(
        TasksStage.task_code == task_code, TasksStage.number == number
    )
    if moving is not None:
        stmt = stmt.where(TasksStage.code != moving)
    holder = (await s.execute(stmt)).first()
    if holder is not None:
        raise ValueError(
            f"Number {number} in task {task_code!r} is taken by stage {holder[0]} "
            f"({holder[1]!r}). Numbers order the plan, they do not count it: move that stage "
            "first, pick a free number, or omit it to append at the end."
        )
    return number


async def stage_create(
    *,
    task_code: str,
    title: str,
    number: int | None = None,
    description: str | None = None,
    body: str | None = None,
) -> TasksStage:
    """Create a stage. No number given — the task's next one; a taken one — refused."""
    async with write_scope() as s:
        await _require_staged_task(s, task_code)
        place = (
            await _free_number(s, task_code, number)
            if number is not None
            else await _next_number(s, task_code)
        )
        row = TasksStage(
            code=new_code(),
            task_code=task_code,
            number=place,
            status=STAGE_STATUS_DEFAULT,
            title=clip(title, TITLE_MAX),
            description=clip(description, DESCRIPTION_MAX),
            body=fit(body, BODY_MAX, "stage body"),
        )
        s.add(row)
        await s.flush()
        await s.refresh(row)
    return row


async def stage_get(code: str) -> TasksStage | None:
    async with session_scope() as s:
        return await s.get(TasksStage, code)


async def stage_list_by_task(task_code: str) -> list[TasksStage]:
    """The task's stages by number, first on top — a plan reads top to bottom."""
    stmt = (
        select(TasksStage)
        .where(TasksStage.task_code == task_code)
        .order_by(TasksStage.number.asc())
    )
    async with session_scope() as s:
        return list((await s.execute(stmt)).scalars().all())


async def stage_update(
    code: str,
    *,
    title: str | None = None,
    description: str | None = None,
    body: str | None = None,
    number: int | None = None,
    evidence: str | None = None,
) -> TasksStage | None:
    """Update the given stage fields (``None`` = leave as is). Returns ``None`` — no such stage."""
    async with write_scope() as s:
        row = await s.get(TasksStage, code)
        if row is None:
            return None
        if title is not None:
            row.title = clip(title, TITLE_MAX)
        if description is not None:
            row.description = clip(description, DESCRIPTION_MAX)
        if body is not None:
            row.body = fit(body, BODY_MAX, "stage body")
        if number is not None:
            # The moving row itself is excluded from the check: otherwise "set it to its own
            # number" would be refused, citing the row itself.
            row.number = await _free_number(s, row.task_code, number, moving=code)
        if evidence is not None:
            row.evidence = clip(evidence, EVIDENCE_MAX)
        await s.flush()
        await s.refresh(row)
    return row


async def stage_update_status(code: str, status: str) -> TasksStage | None:
    """Change a stage's status and set the phase timestamp.

    Closing requires evidence: ``done`` with empty ``evidence`` is a ``ValueError``. Without this
    check a stage could be marked done without a single trace of the work, and the rest of the
    plan would proceed reasoning from a false premise.
    """
    _checked(status, TASK_STATUSES, "stage status")
    async with write_scope() as s:
        row = await s.get(TasksStage, code)
        if row is None:
            return None
        if status == STATUS_DONE and not row.evidence:
            raise TaskRuleError(
                STAGE_EVIDENCE_REQUIRED,
                f"Stage {code!r} has no evidence — fill it with a pointer to the proof "
                "(command and its result, path, diff) before closing the stage.",
            )
        row.status = status
        now = utc_now()
        if status == STATUS_IN_PROGRESS and row.started_at is None:
            row.started_at = now
        if status in TASK_STATUSES_TERMINAL and row.finished_at is None:
            row.finished_at = now
        if status == STATUS_CANCELED and row.started_at is None:
            # A stage abandoned before it started is finished too — otherwise "closed" and "open"
            # stop covering every row, and the plan list starts lying.
            row.finished_at = now
        await s.flush()
        await s.refresh(row)
    return row


async def stage_delete(code: str) -> bool:
    """Hard-delete a stage. ``True`` — the row existed.

    A stage has no soft delete: an abandoned stage is the ``canceled`` status, and a hidden plan
    row would leave the history of the work incomplete.
    """
    async with write_scope() as s:
        row = await s.get(TasksStage, code)
        if row is None:
            return False
        await s.execute(sa_delete(TasksStage).where(TasksStage.code == code))
        # A bulk statement yields no objects — so we name the code to the change feed ourselves.
        mark_changes(s, "tasks.stage", DELETED, [code])
    return True


async def stage_count_by_task_codes(task_codes: list[str]) -> dict[str, int]:
    """``task_code → number of its stages`` in one ``GROUP BY`` — for the task list."""
    if not task_codes:
        return {}
    stmt = (
        select(TasksStage.task_code, func.count())
        .where(TasksStage.task_code.in_(task_codes))
        .group_by(TasksStage.task_code)
    )
    async with session_scope() as s:
        return {code: count for code, count in (await s.execute(stmt)).all()}


__all__ = [
    "stage_count_by_task_codes",
    "stage_create",
    "stage_delete",
    "stage_get",
    "stage_list_by_task",
    "stage_update",
    "stage_update_status",
]
