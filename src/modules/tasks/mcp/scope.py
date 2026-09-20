"""Забор пространства: активное пространство сессии и проверка, что код указывает в него.

Правило одно на всю поверхность: **пространство — жёсткая граница**. Код из чужого пространства
не отрабатывается молча, а отвергается с названиями обоих. Причина не в безопасности — доступ
здесь у всех один, — а в том, что ошибка контура иначе невидима: чужая задача выглядит как
задача, а чужой пустой список как «работы нет».

Тип кода забор не угадывает: его называет вызывающий тем же префиксом, которым снимал
презентационную форму. Угадывание по префиксу сломалось бы на голом коде, а голый код мы
принимаем наравне с ``TASK@…`` — это внутренняя форма, и запрещать её значит запрещать
передавать обратно то, что модуль вернул сам.

Владельца ищем через CRUD соседних сущностей, а не своим запросом: у ``STAGE@``/``NOTE@``
пространство лежит через задачу, и «сколько это стоит» здесь не вопрос — забор срабатывает на
вызов, а не на строку выдачи.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable

from src.modules.tasks.codes import tagged
from src.modules.tasks.constants import (
    GROUP_CODE_PREFIX,
    NOTE_CODE_PREFIX,
    STAGE_CODE_PREFIX,
    TASK_CODE_PREFIX,
)
from src.modules.tasks.crud import group as group_crud
from src.modules.tasks.crud import note as note_crud
from src.modules.tasks.crud import stage as stage_crud
from src.modules.tasks.crud import task as task_crud
from src.modules.workspace.codes import tagged as workspace_tagged
from src.modules.workspace.constants import WORKSPACE_CODE_PREFIX
from src.modules.workspace.crud import workspace as workspace_crud
from src.modules.workspace.mcp import session
from src.modules.workspace.mcp.errors import workspace_mismatch
from src.modules.workspace.models.workspace import Workspace


async def _group_workspace(code: str) -> str | None:
    row = await group_crud.group_get(code, include_deleted=True)
    return row.workspace_code if row else None


async def _task_workspace(code: str) -> str | None:
    row = await task_crud.task_get(code, include_deleted=True)
    return row.workspace_code if row else None


async def _stage_workspace(code: str) -> str | None:
    row = await stage_crud.stage_get(code)
    return await _task_workspace(row.task_code) if row else None


async def _note_workspace(code: str) -> str | None:
    row = await note_crud.note_get(code)
    return await _task_workspace(row.task_code) if row else None


async def _itself(code: str) -> str:
    """Пространство само себе владелец: код сравнивается с активным напрямую."""
    return code


_OWNER: dict[str, Callable[[str], Awaitable[str | None]]] = {
    WORKSPACE_CODE_PREFIX: _itself,
    GROUP_CODE_PREFIX: _group_workspace,
    TASK_CODE_PREFIX: _task_workspace,
    STAGE_CODE_PREFIX: _stage_workspace,
    NOTE_CODE_PREFIX: _note_workspace,
}


async def workspace_of(prefix: str, bare: str) -> str | None:
    """Голый код пространства, которому принадлежит сущность; ``None`` — сущности нет.

    Отсутствие строки забор не трогает: «не найдено» скажет сам инструмент, и своей формулировкой
    — она у него точнее, чем общая.
    """
    owner = _OWNER.get(prefix)
    if owner is None:
        raise ValueError(
            f"{prefix}@ is not an entity of this module — expected one of "
            f"{', '.join(sorted(_OWNER))}."
        )
    return await owner(bare)


async def require_active() -> Workspace:
    """Активное пространство сессии или обучающий отказ. Ничего не проверяет сверх этого."""
    return await session.require_active()


async def require_scope(prefix: str, bare: str) -> Workspace:
    """Активное пространство + проверка, что названная сущность лежит именно в нём.

    Отдаёт пространство, а не ``None``: оно нужно вызывающему следующей же строкой — собрать
    конверт ответа, — и второй запрос за тем, что забор только что прочитал, был бы лишним.
    """
    active = await require_active()
    owner = await workspace_of(prefix, bare)
    if owner is not None and owner != active.code:
        holder = await workspace_crud.workspace_get(owner, include_deleted=True)
        raise workspace_mismatch(
            code=str(tagged(prefix, bare)),
            owner_code=str(workspace_tagged(WORKSPACE_CODE_PREFIX, owner)),
            owner_title=holder.title if holder else "unknown",
            active_code=str(workspace_tagged(WORKSPACE_CODE_PREFIX, active.code)),
            active_title=active.title,
        )
    return active


__all__ = ["require_active", "require_scope", "workspace_of"]
