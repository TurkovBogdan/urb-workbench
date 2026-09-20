"""CRUD ``Workspace`` — рабочие пространства. Каждая функция владеет своей сессией.

Чтения принимают ``include_deleted`` и по умолчанию скрывают логически удалённое: «удалено»
для всего остального кода означает «не существует».

``workspace_delete`` по умолчанию мягкое — и это не формальность: модули поверх ссылаются на
пространство с ``ON DELETE CASCADE``, поэтому ``hard=True`` физически уносит всё их содержимое,
относящееся к этому пространству, без единого шанса на восстановление. Модуль при этом не знает,
кто именно на него ссылается, и знать не должен: каскад описан на дочерней стороне.
"""

from __future__ import annotations

from sqlalchemy import delete as sa_delete, select, update

from src.core.database import session_scope, write_scope
from src.core.utils.date import utc_now
from src.modules.workspace.codes import new_code
from src.modules.workspace.constants import (
    COLOR_MAX,
    DESCRIPTION_MAX,
    ICON_MAX,
    TITLE_MAX,
)
from src.modules.workspace.models.workspace import Workspace
from src.modules.workspace.text import clip


async def workspace_create(
    *,
    title: str,
    description: str | None = None,
    color: str | None = None,
    icon: str | None = None,
) -> Workspace:
    async with write_scope() as s:
        row = Workspace(
            code=new_code(),
            title=clip(title, TITLE_MAX),
            description=clip(description, DESCRIPTION_MAX),
            color=clip(color, COLOR_MAX),
            icon=clip(icon, ICON_MAX),
        )
        s.add(row)
        await s.flush()
        await s.refresh(row)
    return row


async def workspace_get(
    code: str, *, include_deleted: bool = False
) -> Workspace | None:
    stmt = select(Workspace).where(Workspace.code == code)
    if not include_deleted:
        stmt = stmt.where(Workspace.deleted_at.is_(None))
    async with session_scope() as s:
        return (await s.execute(stmt)).scalar_one_or_none()


async def workspace_list(*, include_deleted: bool = False) -> list[Workspace]:
    """Все пространства по названию; ``code`` — стабильный тайбрейк для одинаковых названий."""
    stmt = select(Workspace).order_by(
        Workspace.title.asc(), Workspace.code.asc()
    )
    if not include_deleted:
        stmt = stmt.where(Workspace.deleted_at.is_(None))
    async with session_scope() as s:
        return list((await s.execute(stmt)).scalars().all())


async def workspace_update(
    code: str,
    *,
    title: str | None = None,
    description: str | None = None,
    color: str | None = None,
    icon: str | None = None,
) -> Workspace | None:
    """Обновить переданные поля (``None`` = не трогать, ``""`` = очистить).

    Удалённое пространство не правится: сначала ``workspace_restore``.
    """
    async with write_scope() as s:
        row = await s.get(Workspace, code)
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
        await s.flush()
        await s.refresh(row)
    return row


async def workspace_delete(code: str, *, hard: bool = False) -> bool:
    """Удалить пространство: мягко (по умолчанию) или физически. ``True`` — строка существовала.

    ``hard=True`` уносит каскадом FK всё, что модули поверх держали в этом пространстве, —
    никакой отметки времени после этого не остаётся, восстановить нечего.
    """
    async with write_scope() as s:
        row = await s.get(Workspace, code)
        if row is None:
            return False
        if hard:
            await s.execute(
                sa_delete(Workspace).where(Workspace.code == code)
            )
        else:
            await s.execute(
                update(Workspace)
                .where(Workspace.code == code, Workspace.deleted_at.is_(None))
                .values(deleted_at=utc_now())
            )
    return True


async def workspace_restore(code: str) -> bool:
    """Снять отметку удаления. ``True`` — пространство было удалено и поднято."""
    async with write_scope() as s:
        row = await s.get(Workspace, code)
        if row is None or row.deleted_at is None:
            return False
        row.deleted_at = None
        await s.flush()
    return True


__all__ = [
    "workspace_create",
    "workspace_delete",
    "workspace_get",
    "workspace_list",
    "workspace_restore",
    "workspace_update",
]
