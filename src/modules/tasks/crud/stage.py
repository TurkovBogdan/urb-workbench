"""CRUD ``TasksStage`` — этапы плана. Каждая функция владеет своей сессией.

Два правила живут здесь, а не в схеме, потому что оба смотрят сразу на несколько значений одной
строки и на её соседей:

- **номер по умолчанию** — максимальный по задаче плюс один. Считается в той же транзакции, что
  и вставка: иначе два подряд заведённых этапа получили бы один номер и упёрлись в уникальный
  индекс;
- **закрытие требует доказательства** — переход в ``done`` с пустым ``evidence`` отказывает. Это
  единственное место, где перевод статуса что-то проверяет, и ради него ``stage_update_status``
  существует отдельно от общей правки.

``finished_at`` проставляет система при уходе в терминальный статус, ``started_at`` — при первом
входе в ``in_progress``. Обе отметки — факты, и повторный переход их не перебивает.
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
    """Значение из справочника или ``ValueError`` со списком допустимых."""
    if value not in allowed:
        raise ValueError(f"Unknown {what} {value!r}; expected one of {', '.join(allowed)}.")
    return value


async def _require_staged_task(s, task_code: str) -> None:
    """Живая задача С ЭТАПАМИ или отказ.

    Две проверки, а не одна. Удалённая задача этапов не принимает — это очевидно. А тип
    проверяется потому, что этапы есть **только у расширенной**: это и есть граница между ней и
    стандартной. У стандартной план живёт прозой в теле, и молча заведённый там этап не показал
    бы себя нигде — интерфейс рисует полотно этапов только расширенной, и строка осталась бы
    невидимой обеим сторонам.
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
            "as prose in the body. Either write it there, or raise the type first if the work "
            "really needs steps with their own evidence."
        )


async def _next_number(s, task_code: str) -> int:
    """Максимальный номер этапа задачи плюс один; у первой задачи — единица."""
    stmt = select(func.max(TasksStage.number)).where(TasksStage.task_code == task_code)
    return ((await s.execute(stmt)).scalar_one_or_none() or 0) + 1


async def _free_number(s, task_code: str, number: int, *, moving: str | None = None) -> int:
    """Номер, свободный в этой задаче, — или отказ с именем того, кто его держит.

    Без этой проверки занятый номер упирается в уникальный индекс и возвращает
    ``IntegrityError`` с куском SQL: для человека это шум, для агента — текст, из которого
    нечего понять и нечем починиться. А переработка плана (схлопнуть два этапа, вставить
    третий) — самый обычный ход, и на нём это всплывает первым делом.

    Перенумерация хвоста здесь НЕ делается намеренно: агент ссылается на «третий этап» прозой
    в журнале, и молчаливый сдвиг сделал бы такие ссылки ложными. Дыры в нумерации легальны —
    номер упорядочивает, а не считает.
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
    """Завести этап. Номер не передан — следующий по задаче; занятый — отказ."""
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
    """Этапы задачи по номеру: первый сверху — план читается сверху вниз."""
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
    """Обновить переданные поля этапа (``None`` = не трогать). ``None`` в ответе — этапа нет."""
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
            # Сама переезжающая строка из проверки исключена: иначе «поставить на свой же
            # номер» отказывало бы, ссылаясь на саму себя.
            row.number = await _free_number(s, row.task_code, number, moving=code)
        if evidence is not None:
            row.evidence = clip(evidence, EVIDENCE_MAX)
        await s.flush()
        await s.refresh(row)
    return row


async def stage_update_status(code: str, status: str) -> TasksStage | None:
    """Сменить статус этапа и проставить отметку фазы.

    Закрытие требует доказательства: ``done`` с пустым ``evidence`` — ``ValueError``. Без этой
    проверки этап помечался бы сделанным без единого следа работы, а дальше по плану шли бы
    рассуждения на ложной посылке.
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
            # Брошенный до старта этап тоже завершён — иначе «закрытые» и «незакрытые» перестают
            # покрывать все строки, и список планов начинает врать.
            row.finished_at = now
        await s.flush()
        await s.refresh(row)
    return row


async def stage_delete(code: str) -> bool:
    """Снести этап физически. ``True`` — строка существовала.

    Логического удаления у этапа нет: брошенный этап — это статус ``canceled``, а спрятанная
    строка плана сделала бы историю работы неполной.
    """
    async with write_scope() as s:
        row = await s.get(TasksStage, code)
        if row is None:
            return False
        await s.execute(sa_delete(TasksStage).where(TasksStage.code == code))
        # Массовый оператор объектов не даёт — ленте изменений код называем сами.
        mark_changes(s, "tasks.stage", DELETED, [code])
    return True


async def stage_count_by_task_codes(task_codes: list[str]) -> dict[str, int]:
    """``task_code → сколько в ней этапов`` одним ``GROUP BY`` — для списка задач."""
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
