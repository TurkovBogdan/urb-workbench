"""CRUD ``TasksGroup`` — группы задач в пространстве. Каждая функция владеет своей сессией.

Согласованность пространства проверяется здесь, на записи: группа заводится только в живом
пространстве, и ссылка на несуществующее пространство — ``ValueError`` с внятным текстом, а не
``IntegrityError`` из недр драйвера. FK в схеме остаётся страховкой на случай записи мимо CRUD.
"""

from __future__ import annotations

from sqlalchemy import delete as sa_delete, func, select, update

from src.core.database import session_scope, write_scope
from src.core.utils.date import utc_now
from src.modules.core_changes import DELETED, UPDATED, mark_changes
from src.modules.tasks.codes import new_code
from src.modules.tasks.constants import (
    COLOR_MAX,
    DESCRIPTION_MAX,
    ICON_MAX,
    SORT_DEFAULT,
    SORT_STEP,
    TITLE_MAX,
)
from src.modules.tasks.models.group import TasksGroup
from src.modules.tasks.text import clip
from src.modules.workspace.models.workspace import Workspace


async def _require_workspace(s, workspace_code: str) -> None:
    """Живое пространство или отказ: ссылка на удалённое — такая же ошибка, как на пропавшее."""
    stmt = select(Workspace.code).where(
        Workspace.code == workspace_code, Workspace.deleted_at.is_(None)
    )
    if (await s.execute(stmt)).scalar_one_or_none() is None:
        raise ValueError(
            f"Workspace {workspace_code!r} does not exist (or is deleted) — "
            "a group always belongs to a live workspace."
        )


async def _sort_at_end(s, workspace_code: str) -> int:
    """Позиция ниже всех живых групп пространства; в пустом — ``SORT_DEFAULT``.

    Считается в той же транзакции, что и вставка: разойтись с чужой одновременной записью
    значение не успеет, а совпадение двух ``sort`` порядок всё равно не ломает — его разводит
    тайбрейк по названию.
    """
    stmt = select(func.min(TasksGroup.sort)).where(
        TasksGroup.workspace_code == workspace_code, TasksGroup.deleted_at.is_(None)
    )
    lowest = (await s.execute(stmt)).scalar_one_or_none()
    return SORT_DEFAULT if lowest is None else lowest - SORT_STEP


async def group_create(
    *,
    workspace_code: str,
    title: str,
    description: str | None = None,
    color: str | None = None,
    icon: str | None = None,
    sort: int | None = None,
) -> TasksGroup:
    """Завести группу; ``sort=None`` — в конец списка, число — на точную позицию.

    Умолчание именно «в конец», а не ``SORT_DEFAULT``: у новой группы с тем же ``sort``, что у
    половины соседей, позиция определяется тайбрейком по названию, то есть случайна с точки
    зрения заводившего. Интерфейс шлёт число сам и этой ветки не касается.
    """
    async with write_scope() as s:
        await _require_workspace(s, workspace_code)
        row = TasksGroup(
            code=new_code(),
            workspace_code=workspace_code,
            title=clip(title, TITLE_MAX),
            description=clip(description, DESCRIPTION_MAX),
            color=clip(color, COLOR_MAX),
            icon=clip(icon, ICON_MAX),
            sort=await _sort_at_end(s, workspace_code) if sort is None else sort,
        )
        s.add(row)
        await s.flush()
        await s.refresh(row)
    return row


async def group_find_by_title(workspace_code: str, title: str) -> TasksGroup | None:
    """Живая группа пространства с таким названием, без учёта регистра; иначе ``None``.

    Нужна не схеме, а тому, кто заводит группу вслепую: уникального индекса на паре
    «пространство + название» нет, и без этой проверки в одной раскладке заводятся «Биллинг» и
    «биллинг». Регистр игнорируется, потому что различать их — значит спорить с человеком,
    который считает это одним словом.

    **Регистр сворачивается в Python, а не в SQL**, и это не вкус. ``lower()`` у SQLite складывает
    только ASCII: «Биллинг» остаётся «Биллинг», и запрос не находит ничего. На PostgreSQL та же
    функция кириллицу свернёт — то есть ``func.lower`` дал бы провайдерам РАЗНОЕ поведение на
    русских названиях, причём на dev-провайдере проверка просто молча не срабатывала бы. Цена —
    чтение групп пространства целиком; их единицы, и вызывающий читает тот же список следующей
    строкой.
    """
    wanted = title.strip().casefold()
    stmt = select(TasksGroup).where(
        TasksGroup.workspace_code == workspace_code, TasksGroup.deleted_at.is_(None)
    )
    async with session_scope() as s:
        rows = list((await s.execute(stmt)).scalars().all())
    return next((row for row in rows if row.title.strip().casefold() == wanted), None)


async def group_get(code: str, *, include_deleted: bool = False) -> TasksGroup | None:
    stmt = select(TasksGroup).where(TasksGroup.code == code)
    if not include_deleted:
        stmt = stmt.where(TasksGroup.deleted_at.is_(None))
    async with session_scope() as s:
        return (await s.execute(stmt)).scalar_one_or_none()


async def group_list_by_workspace(
    workspace_code: str, *, include_deleted: bool = False
) -> list[TasksGroup]:
    """Группы пространства: больший ``sort`` выше, дальше по названию (и по коду — для стабильности)."""
    stmt = (
        select(TasksGroup)
        .where(TasksGroup.workspace_code == workspace_code)
        .order_by(TasksGroup.sort.desc(), TasksGroup.title.asc(), TasksGroup.code.asc())
    )
    if not include_deleted:
        stmt = stmt.where(TasksGroup.deleted_at.is_(None))
    async with session_scope() as s:
        return list((await s.execute(stmt)).scalars().all())


async def group_update(
    code: str,
    *,
    title: str | None = None,
    description: str | None = None,
    color: str | None = None,
    icon: str | None = None,
    sort: int | None = None,
) -> TasksGroup | None:
    """Обновить переданные поля группы (``None`` = не трогать; ``sort=0`` — валидная позиция).

    Пространство группы не меняется: перенести группу между пространствами значит утащить за
    собой все её задачи, а это другая операция, и её никто не заказывал.
    """
    async with write_scope() as s:
        row = await s.get(TasksGroup, code)
        if row is None or row.deleted_at is not None:
            return None
        if title is not None:
            row.title = clip(title, TITLE_MAX)
        if description is not None:
            row.description = clip(description, DESCRIPTION_MAX)
        if color is not None:
            row.color = clip(color, COLOR_MAX)
        if icon is not None:
            row.icon = clip(icon, ICON_MAX)
        if sort is not None:
            row.sort = sort
        await s.flush()
        await s.refresh(row)
    return row


async def group_reorder(
    code: str, *, after: str | None = None, before: str | None = None
) -> TasksGroup | None:
    """Поставить группу прямо под (``after``) или прямо над (``before``) соседней.

    Позиция задаётся соседом, а не числом: ``sort`` — внутренняя механика, и тому, кто двигает
    группу, попасть в него нечем. Ровно одна из двух точек отсчёта обязательна.

    Список после вставки **перенумеровывается целиком** — сверху вниз с шагом ``SORT_STEP``, —
    а записываются только строки, у которых значение реально изменилось. Групп в пространстве
    единицы, поэтому дешёвая арифметика «поделить зазор пополам» не окупается: она добавляет
    вторую ветку на случай кончившегося зазора, и эта ветка живёт непройденной до того дня,
    когда сломается.

    ``None`` — группы нет или она удалена; чужая, удалённая или несуществующая точка отсчёта —
    ``ValueError`` с названием причины.
    """
    if (after is None) == (before is None):
        raise ValueError(
            "Pass exactly one of after / before — a position needs one point of reference."
        )
    anchor_code = after or before
    async with write_scope() as s:
        row = await s.get(TasksGroup, code)
        if row is None or row.deleted_at is not None:
            return None
        if anchor_code == code:
            raise ValueError(
                f"Group {code!r} cannot be placed relative to itself — name another group."
            )
        anchor = await s.get(TasksGroup, anchor_code)
        if anchor is None or anchor.deleted_at is not None:
            raise ValueError(f"Group {anchor_code!r} does not exist (or is deleted).")
        if anchor.workspace_code != row.workspace_code:
            raise ValueError(
                f"Group {anchor_code!r} belongs to workspace {anchor.workspace_code!r}, but "
                f"{code!r} belongs to {row.workspace_code!r} — a layout never spans workspaces."
            )
        siblings = list(
            (
                await s.execute(
                    select(TasksGroup)
                    .where(
                        TasksGroup.workspace_code == row.workspace_code,
                        TasksGroup.deleted_at.is_(None),
                    )
                    .order_by(
                        TasksGroup.sort.desc(),
                        TasksGroup.title.asc(),
                        TasksGroup.code.asc(),
                    )
                )
            )
            .scalars()
            .all()
        )
        ordered = [item for item in siblings if item.code != code]
        at = next(i for i, item in enumerate(ordered) if item.code == anchor_code)
        ordered.insert(at + 1 if after else at, row)
        top = SORT_DEFAULT + (len(ordered) - 1) * SORT_STEP
        for position, item in enumerate(ordered):
            place = top - position * SORT_STEP
            if item.sort != place:
                item.sort = place
        await s.flush()
        await s.refresh(row)
    return row


async def group_delete(code: str, *, hard: bool = False) -> bool:
    """Удалить группу: мягко (по умолчанию) или физически. ``True`` — строка существовала.

    Задачи группы переживают её в обоих случаях: при ``hard=True`` FK ``SET NULL`` просто снимает
    у них разложенность. При мягком удалении ``group_code`` у задач остаётся — чтобы
    ``group_restore`` вернул раскладку ровно в том виде, в каком её сняли.
    """
    async with write_scope() as s:
        row = await s.get(TasksGroup, code)
        if row is None:
            return False
        # Массовые операторы объектов не дают — ленте изменений код называем сами.
        if hard:
            await s.execute(sa_delete(TasksGroup).where(TasksGroup.code == code))
            mark_changes(s, "tasks.group", DELETED, [code])
        else:
            await s.execute(
                update(TasksGroup)
                .where(TasksGroup.code == code, TasksGroup.deleted_at.is_(None))
                .values(deleted_at=utc_now())
            )
            mark_changes(s, "tasks.group", UPDATED, [code])
    return True


async def group_restore(code: str) -> bool:
    """Снять отметку удаления. ``True`` — группа была удалена и поднята."""
    async with write_scope() as s:
        row = await s.get(TasksGroup, code)
        if row is None or row.deleted_at is None:
            return False
        row.deleted_at = None
        await s.flush()
    return True


async def group_count_by_workspace_codes(
    workspace_codes: list[str], *, include_deleted: bool = False
) -> dict[str, int]:
    """``workspace_code → сколько в нём групп`` одним ``GROUP BY`` — для списка пространств.

    Считается разом на весь список: карточек на экране десяток, и запрос на каждую дал бы
    N+1 там, где хватает одной группировки. Пространства без групп в ответе нет — ноль
    подставляет вызывающий, чтобы отличать «не считали» от «ничего не нашли».
    """
    if not workspace_codes:
        return {}
    stmt = (
        select(TasksGroup.workspace_code, func.count())
        .where(TasksGroup.workspace_code.in_(workspace_codes))
        .group_by(TasksGroup.workspace_code)
    )
    if not include_deleted:
        stmt = stmt.where(TasksGroup.deleted_at.is_(None))
    async with session_scope() as s:
        return {code: count for code, count in (await s.execute(stmt)).all()}


__all__ = [
    "group_count_by_workspace_codes",
    "group_create",
    "group_delete",
    "group_find_by_title",
    "group_get",
    "group_list_by_workspace",
    "group_reorder",
    "group_restore",
    "group_update",
]
