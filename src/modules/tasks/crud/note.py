"""CRUD ``TasksNote`` — журнал работы. Каждая функция владеет своей сессией.

Таблица дописываемая, и слой это держит: правки записи нет вовсе, а ``note_resolve`` заполняет
разрешение **один раз**. Повторный вызов на уже закрытой записи отказывает — иначе историю можно
было бы переписать под результат, и разбор неудачи перестал бы что-либо значить. Отмена
оформляется новой записью, а не правкой старой.

Кто пишет какую половину строки, слой не решает: это поверхность (MCP/HTTP) — у агента просто нет
инструмента завести ``remark`` и нет ручки проставить ответ там, где отвечает человек.

Открытая запись — та, у которой пусто ``resolution``. ``fact`` закрыт в момент создания, поэтому
в счётчик открытых не попадает: он ничего не ждёт.
"""

from __future__ import annotations

from sqlalchemy import delete as sa_delete, func, select

from src.core.database import session_scope, write_scope
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
    """Живая задача С ПЛАНОМ или отказ — те же две проверки, что и у этапа.

    Журнал начинается с ``standard`` по той же причине, что и этапы: у ``simple`` его нет ни в
    схеме ведения, ни в интерфейсе, и запись туда никому бы не показалась.
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
    """Этап существует и принадлежит той же задаче, что и запись."""
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
    """Завести запись журнала.

    ``resolution`` на создании имеет смысл ровно для ``fact``: факт закрыт в момент записи, ждать
    ему нечего. Остальные виды заводятся открытыми и закрываются ``note_resolve``.
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
    """Журнал задачи в порядке появления; можно сузить до вида или до незакрытых записей."""
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
    """Закрыть запись разрешением. ``None`` — записи нет; уже закрытая — ``TaskRuleError``.

    Пробелы срезаются ДО проверки на пустоту: иначе строка из одних пробелов закрывала бы запись,
    оставляя её пустой на вид — и открытой по смыслу, но закрытой для шлюза.
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
    """Снести запись физически. Агенту эта операция не отдаётся — журнал чистит человек."""
    async with write_scope() as s:
        row = await s.get(TasksNote, code)
        if row is None:
            return False
        await s.execute(sa_delete(TasksNote).where(TasksNote.code == code))
    return True


async def note_open_count_by_task_codes(
    task_codes: list[str], *, types: tuple[str, ...] = NOTE_TYPES_OPENABLE
) -> dict[str, int]:
    """``task_code → сколько открытых записей`` названных видов.

    ``fact`` не входит в ``NOTE_TYPES_OPENABLE`` вовсе: он закрыт в момент записи и ничего не
    ждёт. Остальные три — ждут, но ждут **разного**, и потому у счётчика есть параметр.

    Для показа человеку считают всё открытое. Для **шлюза сдачи** — только
    ``NOTE_TYPES_BLOCKING`` (решение и замечание): их закрыть в силах тот, кто сдаёт работу.
    Находка адресована не сюда — её разбирает человек в своём порядке, и посчитай мы её
    наравне, первая же находка заперла бы сдачу навсегда, потому что снять её исполнителю
    нечем.
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
