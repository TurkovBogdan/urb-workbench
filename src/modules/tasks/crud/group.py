"""CRUD ``TasksGroup`` — группы задач в пространстве. Каждая функция владеет своей сессией.

Согласованность пространства проверяется здесь, на записи: группа заводится только в живом
пространстве, и ссылка на несуществующее пространство — ``ValueError`` с внятным текстом, а не
``IntegrityError`` из недр драйвера. FK в схеме остаётся страховкой на случай записи мимо CRUD.
"""

from __future__ import annotations

from sqlalchemy import delete as sa_delete, func, select, update

from src.core.database import session_scope, write_scope
from src.core.utils.date import utc_now
from src.modules.tasks.codes import new_code
from src.modules.tasks.constants import (
    COLOR_MAX,
    DESCRIPTION_MAX,
    ICON_MAX,
    SORT_DEFAULT,
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


async def group_create(
    *,
    workspace_code: str,
    title: str,
    description: str | None = None,
    color: str | None = None,
    icon: str | None = None,
    sort: int = SORT_DEFAULT,
) -> TasksGroup:
    async with write_scope() as s:
        await _require_workspace(s, workspace_code)
        row = TasksGroup(
            code=new_code(),
            workspace_code=workspace_code,
            title=clip(title, TITLE_MAX),
            description=clip(description, DESCRIPTION_MAX),
            color=clip(color, COLOR_MAX),
            icon=clip(icon, ICON_MAX),
            sort=sort,
        )
        s.add(row)
        await s.flush()
        await s.refresh(row)
    return row


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
        if hard:
            await s.execute(sa_delete(TasksGroup).where(TasksGroup.code == code))
        else:
            await s.execute(
                update(TasksGroup)
                .where(TasksGroup.code == code, TasksGroup.deleted_at.is_(None))
                .values(deleted_at=utc_now())
            )
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
    "group_get",
    "group_list_by_workspace",
    "group_restore",
    "group_update",
]
