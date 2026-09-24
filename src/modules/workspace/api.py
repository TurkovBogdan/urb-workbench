"""HTTP-API модуля ``workspace`` (монтируется на ``/internal/workspace`` — см. ``module.py``).

Одна поверхность — само пространство: список, создание, чтение, правка, мягкое удаление,
восстановление и физическое удаление. Заводит и правит его человек (это его раскладка, а не
результат работы агента), поэтому набор ручек полный.

**Два удаления — две разные ручки, и это намеренно.** ``DELETE /workspace/{code}`` ставит
отметку: содержимое остаётся на месте, список без флага его не показывает, ``restore`` возвращает
всё как было. ``DELETE /workspace/{code}/purge`` сносит строку физически, а вместе с ней
каскадом FK — всё, что модули поверх держали в этом пространстве. Спрятать второе под флагом
первого значило бы, что необратимое отличается от обратимого одним символом в адресе.

**Счётчики едут со строкой списка, но не принадлежат модулю.** Что лежит внутри пространства,
знают модули поверх; они же объявляют счётчики (``stats.py``), а список лишь собирает
объявленное. Поэтому набор чисел в ответе зависит от состава приложения, и пустой список —
законный ответ. Без них диалог удаления сообщал бы «содержимое исчезнет», не называя, сколько
именно, — то есть просил бы подтвердить неизвестное.

**Незнакомое поле в теле — отказ, а не тишина** (``_Body`` на ``extra="forbid"``): опечатка в
имени поля иначе проезжает молча и даёт 201 с карточкой, где этого значения нет.

**Код на входе принимается в обеих формах** — ``WORKSPACE@<hash>`` и голый хеш: первую человек
копирует из интерфейса, вторую модули отдают друг другу изнутри. Префикс кода назван по сущности
и переименование модуля его не касается. Чужой префикс (``GROUP@``) — не
«не найдено», а перепутанный аргумент, и отвечаем мы на него 400, а не 404, который увёл бы к
мысли, что запись удалили.

Зона ``internal`` в чистом ядре открыта (``allow_all``), guard не нужен.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Query, Response
from pydantic import BaseModel, ConfigDict, Field, StringConstraints

from src.core.api import ApiError
from src.modules.workspace import stats
from src.modules.workspace.codes import bare_code
from src.modules.workspace.constants import (
    COLOR_MAX,
    DESCRIPTION_MAX,
    ICON_MAX,
    TITLE_MAX,
    WORKSPACE_CODE_PREFIX,
)
from src.modules.workspace.crud import workspace as workspace_crud
from src.modules.workspace.errors import WORKSPACE_DELETED, WORKSPACE_NOT_DELETED, WORKSPACE_NOT_FOUND
from src.modules.workspace.dto import (
    WorkspaceCounterRow,
    WorkspaceListRow,
    WorkspaceRow,
)
from src.modules.workspace.models.workspace import Workspace

router = APIRouter()


class _Body(BaseModel):
    """Общий предок всех тел запроса: незнакомое поле — отказ, а не тишина.

    ``extra="forbid"`` стоит здесь, а не на каждой модели отдельно, ровно чтобы новая ручка не
    могла завестись без него. На ответных DTO (``dto.py``) запрет не нужен и вреден: их собираем
    мы сами, а ``from_attributes`` читает атрибуты ORM-строки, где лишнего не бывает.
    """

    model_config = ConfigDict(extra="forbid")


class WorkspaceBody(_Body):
    """Тело создания и правки пространства — один набор полей на обе ручки.

    Обрамляющие пробелы у названия срезаются ДО проверки длины, поэтому имя из одних пробелов
    отвергается наравне с пустым: пространство без названия неразличимо в списке, а «стереть
    название» — не сценарий. Описание пустым быть вправе: оно необязательно.

    Имена цвета и иконки с палитрами не сверяются — по той же причине, по которой их не проверяет
    БД: рисовать их умеет только фронт, и он же переживёт незнакомое имя, а проверка здесь
    превратила бы расширение палитры в правку двух файлов на двух языках.
    """

    title: Annotated[
        str, StringConstraints(strip_whitespace=True, min_length=1, max_length=TITLE_MAX)
    ]
    description: Annotated[
        str, StringConstraints(strip_whitespace=True, max_length=DESCRIPTION_MAX)
    ] = ""
    color: str = Field(default="", max_length=COLOR_MAX)
    icon: str = Field(default="", max_length=ICON_MAX)


def _code(value: str) -> str:
    """Голый код пространства из сегмента адреса; чужой тип — 400, а не 404.

    ``bare_code`` отличает «код другой сущности» от «кода нет»: первое чинится правкой вызова,
    второе — нет, и путать их в ответе значит отправлять клиента искать несуществующую пропажу.
    """
    try:
        return bare_code(value, WORKSPACE_CODE_PREFIX) or ""
    except ValueError as error:
        raise ApiError.bad_request(str(error)) from error


async def _require(code: str) -> Workspace:
    """Пространство любого состояния или 404.

    Удалённое ищется наравне с живым (``include_deleted=True``): его показывают в списке,
    восстанавливают и сносят насовсем — для всех трёх сценариев «не найдено» означало бы, что
    ручка не видит того, что человек прямо сейчас видит на экране.
    """
    row = await workspace_crud.workspace_get(code, include_deleted=True)
    if row is None:
        raise ApiError.not_found("Workspace not found", code=WORKSPACE_NOT_FOUND)
    return row


@router.get("")
async def list_workspaces(
    include_deleted: bool = Query(
        False, description="Показать и удалённые пространства (с отметкой ``deleted_at``)"
    ),
) -> list[WorkspaceListRow]:
    """Пространства по названию + счётчики, объявленные модулями поверх.

    Пагинации нет намеренно: пространство — верхний уровень раскладки, их заводят единицами, и
    страница здесь была бы органом, который нечего листать.
    """
    rows = await workspace_crud.workspace_list(include_deleted=include_deleted)
    codes = [row.code for row in rows]
    counted = await stats.counts_for(codes)
    specs = stats.registered_counters()
    return [
        WorkspaceListRow(
            **WorkspaceRow.model_validate(row).model_dump(),
            counters=[
                WorkspaceCounterRow(
                    key=spec.key,
                    label_key=spec.label_key,
                    count=counted[row.code][spec.key],
                )
                for spec in specs
            ],
        )
        for row in rows
    ]


@router.post("", status_code=201)
async def create_workspace(payload: WorkspaceBody) -> WorkspaceRow:
    row = await workspace_crud.workspace_create(
        title=payload.title,
        description=payload.description,
        color=payload.color,
        icon=payload.icon,
    )
    return WorkspaceRow.model_validate(row)


@router.get("/{code}")
async def get_workspace(code: str) -> WorkspaceRow:
    """Одно пространство — в том числе удалённое: его состояние видно по ``deleted_at``."""
    return WorkspaceRow.model_validate(await _require(_code(code)))


@router.put("/{code}")
async def update_workspace(code: str, payload: WorkspaceBody) -> WorkspaceRow:
    """Полная замена карточки: тело несёт все четыре поля, пустое значение стирает своё.

    Удалённое не правится — сначала ``restore``. Отвечаем 409, а не 404: запись существует и
    человек её видит в списке удалённых, просто эта операция сейчас не её.
    """
    bare = _code(code)
    existing = await _require(bare)
    if existing.deleted_at is not None:
        raise ApiError.conflict("Workspace is deleted — restore it first", code=WORKSPACE_DELETED)
    row = await workspace_crud.workspace_update(
        bare,
        title=payload.title,
        description=payload.description,
        color=payload.color,
        icon=payload.icon,
    )
    if row is None:
        raise ApiError.not_found("Workspace not found", code=WORKSPACE_NOT_FOUND)
    return WorkspaceRow.model_validate(row)


@router.delete("/{code}", status_code=204)
async def delete_workspace(code: str) -> Response:
    """Мягкое удаление: содержимое остаётся, список без флага его не показывает.

    Повторное удаление уже удалённого не ошибка: CRUD не трогает строку с отметкой, и результат
    совпадает с желаемым — пространство удалено.
    """
    if not await workspace_crud.workspace_delete(_code(code)):
        raise ApiError.not_found("Workspace not found", code=WORKSPACE_NOT_FOUND)
    return Response(status_code=204)


@router.post("/{code}/restore")
async def restore_workspace(code: str) -> WorkspaceRow:
    """Снять отметку удаления и вернуть карточку — её тут же показывает список.

    Живое пространство восстановить нельзя: это не «уже хорошо», а признак того, что кнопку
    нажали не на той строке (например, список успел обновиться), и молчаливое «ок» скрыло бы
    расхождение того, что на экране, с тем, что в базе.
    """
    bare = _code(code)
    existing = await _require(bare)
    if existing.deleted_at is None:
        raise ApiError.conflict("Workspace is not deleted — nothing to restore", code=WORKSPACE_NOT_DELETED)
    await workspace_crud.workspace_restore(bare)
    return WorkspaceRow.model_validate(await _require(bare))


@router.delete("/{code}/purge", status_code=204)
async def purge_workspace(code: str) -> Response:
    """Физическое удаление: строка уходит из таблицы, каскад FK уносит содержимое модулей поверх.

    Отдельный адрес, а не флаг у мягкого удаления: разница между «можно вернуть» и «вернуть
    нечего» не должна прятаться в query-параметре, который легко потерять при копировании
    вызова. Отметки времени после этого не остаётся — восстанавливать нечего и неоткуда.
    """
    if not await workspace_crud.workspace_delete(_code(code), hard=True):
        raise ApiError.not_found("Workspace not found", code=WORKSPACE_NOT_FOUND)
    return Response(status_code=204)


__all__ = ["router"]
