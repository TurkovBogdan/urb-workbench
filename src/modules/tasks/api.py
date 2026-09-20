"""HTTP-API модуля ``tasks`` (монтируется на ``/internal/workbench`` — см. ``module.py``).

Две поверхности: **группы** (долгоживущие темы внутри пространства) и **задачи**. Само
пространство живёт в модуле уровнем ниже (``workspace``) и своё API имеет там же — здесь его код
только принимается параметром и проверяется.

Ни одна выборка не ходит поперёк пространств — поэтому у списков групп и задач ``workspace``
обязателен: без него «все задачи» означало бы смесь работы и личного в одном ответе.

Набор ручек у групп и задач полный: список, создание, чтение, правка, мягкое удаление,
восстановление и физическое удаление — с одной разницей: пространство группы задаётся при
создании и правкой не меняется, потому что перенос группы утащил бы за собой все её задачи.

**Статус задачи меняется отдельной ручкой** (``POST /tasks/{code}/status``), а общая правка его
не принимает. Причина в том, что переход статуса — не запись значения в колонку: он ставит
отметку фазы (начало, завершение, отмена), и её ставит ``task_update_status``. Разреши мы
статус в общей правке — рядом появился бы второй путь смены, у которого отметку поставить
некому, и «сделано» без ``completed_at`` уже ничем нельзя было бы объяснить.

**Место задачи в дереве едет в её же строке** (``parent_code`` / ``sort``), хотя
живёт в отдельной таблице: разделение нужно записи (перенос ветки не переписывает карточку), а
читающему списку нужны обе половины сразу. Меняет их тоже отдельная ручка — ``move``: перенос
это операция над деревом, а не правка поля карточки.

**Два удаления — две разные ручки, и это намеренно.** ``DELETE /groups/{code}`` (как и у задачи)
ставит отметку: содержимое остаётся на месте, список без флага его не показывает, ``restore``
возвращает всё как было. ``DELETE /groups/{code}/purge`` сносит строку физически. Спрятать второе
под флагом первого значило бы, что необратимое отличается от обратимого одним символом в адресе.

**Счётчики содержимого пространства объявляются отсюда**, а не спрашиваются оттуда: карточке
пространства нужны числа «сколько внутри групп и задач», но знать про группы и задачи модуль
уровнем ниже не может. Мы регистрируем их в его реестре (``workspace.stats``) в ``module.py``.

**Незнакомое поле в теле — отказ, а не тишина.** Все модели входа стоят на ``extra="forbid"``
(``_Body``): опечатка в имени поля раньше проезжала молча — ``parent`` вместо ``parent_code``
давал 201 и задачу без родителя, и узнать об этом можно было только по тому, что задача не
встала в ветку. Теперь такой запрос отвечает 422 с ``fields``, где ключ — само лишнее имя.

**Коды на входе принимаются в обеих формах** — ``WORKSPACE@<hash>`` и голый хеш: первую человек
копирует из интерфейса, вторую модуль отдаёт сам изнутри. Чужой префикс (``GROUP@`` вместо
``WORKSPACE@``) — не «не найдено», а перепутанный аргумент, и отвечаем мы на него 400 с
названием обоих типов, а не 404, который увёл бы к мысли, что запись удалили.

Зона ``internal`` в чистом ядре открыта (``allow_all``), guard не нужен.
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Query, Response
from pydantic import BaseModel, ConfigDict, Field, StringConstraints

from src.core.api import ApiError
from src.modules.tasks.codes import bare_code
from src.modules.tasks.constants import (
    COLOR_MAX,
    DESCRIPTION_MAX,
    GROUP_CODE_PREFIX,
    ICON_MAX,
    NOTE_CODE_PREFIX,
    SORT_DEFAULT,
    STAGE_CODE_PREFIX,
    TASK_CODE_PREFIX,
    TASK_PRIORITY_DEFAULT,
    TASK_STATUS_DEFAULT,
    TASK_TYPE_DEFAULT,
    TITLE_MAX,
)
from src.modules.tasks.crud import group as group_crud
from src.modules.tasks.crud import link as link_crud
from src.modules.tasks.crud import note as note_crud
from src.modules.tasks.crud import stage as stage_crud
from src.modules.tasks.crud import task as task_crud
from src.modules.tasks.errors import TaskRuleError
from src.modules.tasks.dto import (
    GroupListRow,
    GroupRow,
    NoteRow,
    StageRow,
    TaskDetail,
    TaskListRow,
    TaskRow,
)
from src.modules.tasks.models.task import TasksTask
from src.modules.workspace.constants import WORKSPACE_CODE_PREFIX
from src.modules.workspace.crud import workspace as workspace_crud
from src.modules.workspace.models.workspace import Workspace

router = APIRouter()


class _Body(BaseModel):
    """Общий предок всех тел запроса: незнакомое поле — отказ, а не тишина.

    ``extra="forbid"`` стоит здесь, а не на каждой модели отдельно, ровно чтобы новая ручка не
    могла завестись без него: молчаливое игнорирование лишнего поля — самая дорогая из мелких
    ошибок контракта. Отправленный ``parent`` вместо ``parent_code`` отвечал 201 и создавал
    задачу без родителя; разницу было видно только по тому, что задача не встала в ветку.

    На ответных DTO (``dto.py``) запрет не нужен и вреден: их собираем мы сами, а
    ``from_attributes`` читает атрибуты ORM-строки, где лишнего не бывает.
    """

    model_config = ConfigDict(extra="forbid")


def _bare(value: str | None, prefix: str) -> str | None:
    """Голый код нужного типа; чужой тип — 400, а не 404.

    ``bare_code`` отличает «код другой сущности» от «кода нет»: первое чинится правкой вызова,
    второе — нет, и путать их в ответе значит отправлять клиента искать несуществующую пропажу.
    """
    try:
        return bare_code(value, prefix)
    except ValueError as error:
        raise ApiError.bad_request(str(error)) from error


def _code(value: str) -> str:
    """Голый код пространства из сегмента адреса или из параметра ``workspace``."""
    return _bare(value, WORKSPACE_CODE_PREFIX) or ""


def _task_code(value: str) -> str:
    """Голый код задачи из сегмента адреса."""
    return _bare(value, TASK_CODE_PREFIX) or ""


async def _require_workspace(code: str) -> Workspace:
    """Живое или удалённое пространство — или 404.

    Пространство принадлежит модулю уровнем ниже (``workspace``), поэтому спрашиваем мы его
    через его же CRUD, а не своим запросом к чужой таблице: у нас на неё есть FK, но не права
    решать, что такое «существует» для чужой сущности.

    Удалённое ищется наравне с живым (``include_deleted=True``): группы и задачи удалённого
    пространства показываются в интерфейсе, и «не найдено» означало бы, что ручка не видит того,
    что человек прямо сейчас видит на экране.
    """
    row = await workspace_crud.workspace_get(code, include_deleted=True)
    if row is None:
        raise ApiError.not_found("Пространство не найдено")
    return row


# ── группы ────────────────────────────────────────────────────────────────────


class GroupBody(_Body):
    """Тело создания и правки группы — один набор полей на обе ручки.

    Пространства здесь нет намеренно: при создании оно приходит параметром запроса (группа
    заводится ВНУТРИ него), а сменить его правкой нельзя вовсе — перенос группы утащил бы за
    собой все её задачи, и это другая операция.

    ``sort`` — позиция среди соседей, больший выше. У него есть умолчание, поэтому форма, которой
    порядок безразличен, может его не слать.
    """

    title: Annotated[
        str, StringConstraints(strip_whitespace=True, min_length=1, max_length=TITLE_MAX)
    ]
    description: Annotated[
        str, StringConstraints(strip_whitespace=True, max_length=DESCRIPTION_MAX)
    ] = ""
    color: str = Field(default="", max_length=COLOR_MAX)
    icon: str = Field(default="", max_length=ICON_MAX)
    sort: int = SORT_DEFAULT


def _group_code(value: str) -> str:
    """Голый код группы из сегмента адреса."""
    return _bare(value, GROUP_CODE_PREFIX) or ""


async def _require_group(code: str):
    """Группа любого состояния или 404 — по той же причине, что и у пространства."""
    row = await group_crud.group_get(code, include_deleted=True)
    if row is None:
        raise ApiError.not_found("Группа не найдена")
    return row


@router.get("/groups")
async def list_groups(
    workspace: str = Query(..., description="Код пространства (``WORKSPACE@…`` или голый)"),
    include_deleted: bool = Query(False, description="Показать и удалённые группы"),
) -> list[GroupListRow]:
    """Группы пространства сверху вниз + сколько живых задач в каждой.

    Пространство обязательно: группа вне его не существует, а «все группы» смешали бы раскладки
    разных пространств в один список, где одинаковые названия («Интерфейс») ничем не различить.
    """
    bare = _code(workspace)
    await _require_workspace(bare)
    rows = await group_crud.group_list_by_workspace(bare, include_deleted=include_deleted)
    tasks = await task_crud.task_count_by_group_codes([row.code for row in rows])
    return [
        GroupListRow(
            **GroupRow.model_validate(row).model_dump(),
            task_count=tasks.get(row.code, 0),
        )
        for row in rows
    ]


@router.post("/groups", status_code=201)
async def create_group(
    payload: GroupBody,
    workspace: str = Query(..., description="Код пространства, в котором заводится группа"),
) -> GroupRow:
    """Завести группу в пространстве. Мёртвое пространство — отказ, и его называет CRUD."""
    bare = _code(workspace)
    await _require_workspace(bare)
    try:
        row = await group_crud.group_create(
            workspace_code=bare,
            title=payload.title,
            description=payload.description,
            color=payload.color,
            icon=payload.icon,
            sort=payload.sort,
        )
    except ValueError as error:
        raise ApiError.conflict(str(error)) from error
    return GroupRow.model_validate(row)


@router.get("/groups/{code}")
async def get_group(code: str) -> GroupRow:
    """Одна группа — в том числе удалённая: её состояние видно по ``deleted_at``."""
    return GroupRow.model_validate(await _require_group(_group_code(code)))


@router.put("/groups/{code}")
async def update_group(code: str, payload: GroupBody) -> GroupRow:
    """Полная замена карточки группы; удалённая не правится — сначала ``restore`` (409)."""
    bare = _group_code(code)
    existing = await _require_group(bare)
    if existing.deleted_at is not None:
        raise ApiError.conflict("Группа удалена — сначала восстановите её")
    row = await group_crud.group_update(
        bare,
        title=payload.title,
        description=payload.description,
        color=payload.color,
        icon=payload.icon,
        sort=payload.sort,
    )
    if row is None:
        raise ApiError.not_found("Группа не найдена")
    return GroupRow.model_validate(row)


@router.delete("/groups/{code}", status_code=204)
async def delete_group(code: str) -> Response:
    """Мягкое удаление: задачи группы остаются на месте и держат ссылку на неё.

    Именно поэтому удаление группы обратимо без следа: ``restore`` возвращает раскладку ровно в
    том виде, в каком её сняли, — задачи не пришлось раскладывать заново.
    """
    if not await group_crud.group_delete(_group_code(code)):
        raise ApiError.not_found("Группа не найдена")
    return Response(status_code=204)


@router.post("/groups/{code}/restore")
async def restore_group(code: str) -> GroupRow:
    """Снять отметку удаления. Живую группу восстановить нельзя — 409, как и у пространства."""
    bare = _group_code(code)
    existing = await _require_group(bare)
    if existing.deleted_at is None:
        raise ApiError.conflict("Группа не удалена — восстанавливать нечего")
    await group_crud.group_restore(bare)
    return GroupRow.model_validate(await _require_group(bare))


@router.delete("/groups/{code}/purge", status_code=204)
async def purge_group(code: str) -> Response:
    """Физическое удаление группы. Задачи переживают её: FK ``SET NULL`` снимает разложенность.

    То есть снос группы — не снос работы: задачи уходят в секцию «Без группы», а не в корзину.
    """
    if not await group_crud.group_delete(_group_code(code), hard=True):
        raise ApiError.not_found("Группа не найдена")
    return Response(status_code=204)


# ── задачи ────────────────────────────────────────────────────────────────────


class TaskCreateBody(_Body):
    """Тело создания задачи: обязательны только пространство и заголовок.

    Всё остальное имеет умолчание на уровне колонки (``backlog`` / ``normal`` / ``simple``),
    поэтому требовать его на входе значило бы заставлять клиента повторять то, что модуль и так
    знает. Справочные значения здесь не проверяются — это делает CRUD, и его отказ называет
    список допустимых; вторая копия перечислений в API разошлась бы с ним при первом же новом
    статусе.

    ``created_by`` в теле нет: автора называет не клиент, а сама поверхность. Эта — человеческая
    (её зовёт интерфейс), и любое значение отсюда было бы словом на веру.
    """

    workspace: str
    title: Annotated[
        str, StringConstraints(strip_whitespace=True, min_length=1, max_length=TITLE_MAX)
    ]
    description: Annotated[
        str, StringConstraints(strip_whitespace=True, max_length=DESCRIPTION_MAX)
    ] = ""
    context: str = ""
    constraints: str = ""
    criteria: str = ""
    body: str = ""
    type: str = TASK_TYPE_DEFAULT
    status: str = TASK_STATUS_DEFAULT
    priority: str = TASK_PRIORITY_DEFAULT
    group_code: str | None = None
    parent_code: str | None = None
    deadline_at: datetime | None = None


class TaskUpdateBody(_Body):
    """Тело правки задачи — полная замена карточки: не переданное поле стирается.

    Замена, а не «поправь названное», ровно по тому же соображению, что и у пространства: форма
    интерфейса всегда отправляет карточку целиком, и тогда единственный способ снять срок или
    группу — отсутствие значения. Разреши мы частичную правку, «стереть» и «не трогать» стали бы
    неразличимы, и однажды поставленная дата не снималась бы вовсе.

    Статуса здесь нет — см. ``POST /tasks/{code}/status``.
    """

    title: Annotated[
        str, StringConstraints(strip_whitespace=True, min_length=1, max_length=TITLE_MAX)
    ]
    description: Annotated[
        str, StringConstraints(strip_whitespace=True, max_length=DESCRIPTION_MAX)
    ] = ""
    context: str = ""
    constraints: str = ""
    criteria: str = ""
    body: str = ""
    type: str = TASK_TYPE_DEFAULT
    priority: str = TASK_PRIORITY_DEFAULT
    group_code: str | None = None
    deadline_at: datetime | None = None


class TaskStatusBody(_Body):
    """Один статус — и ничего больше: у перехода нет других параметров."""

    status: str


class TaskMoveBody(_Body):
    """Новое место задачи в дереве: под кем и на какой позиции.

    Пустой ``parent_code`` — корень пространства, а не «не менять родителя»: перенос всегда
    называет место целиком, и «оставить как есть» выражается тем, что ручку не зовут.
    ``sort`` без значения ставит задачу в конец списка новых соседей — самый частый случай
    («перенеси туда»), ради которого не хочется считать позиции на клиенте.
    """

    parent_code: str | None = None
    sort: int | None = None


class TaskReorderBody(_Body):
    """Одно перетаскивание: где строка теперь стоит и в какой она группе.

    ``after_code`` — задача, ПОСЛЕ которой лёг переезжающий (пусто — в начало ряда). Позиция
    названа соседом, а не номером: у списка на экране свои фильтры и страницы, и номер строки в
    нём не совпадает с номером среди соседей в базе.

    ``group_code`` отсутствует в теле — группу не трогаем; ``null`` — снять группу. Различие
    читается по ``model_fields_set``: перетаскивание внутри одной группы не должно ничего знать
    про группы, а перетаскивание в «Без группы» обязано уметь её снять, и одним ``None`` эти два
    случая не различить.
    """

    after_code: str | None = None
    group_code: str | None = None


async def _require_task(code: str) -> TasksTask:
    """Задача любого состояния или 404.

    Удалённая ищется наравне с живой: её показывает список с флагом, её восстанавливают и сносят
    насовсем — во всех трёх сценариях «не найдено» означало бы, что ручка не видит того, что
    человек прямо сейчас видит на экране.
    """
    row = await task_crud.task_get(code, include_deleted=True)
    if row is None:
        raise ApiError.not_found("Задача не найдена")
    return row


def _live(row: TasksTask) -> None:
    """Операции над карточкой запрещены, пока задача в корзине: сначала ``restore``.

    409, а не 404: запись существует и человек видит её в списке удалённых — просто эта
    операция сейчас не её.
    """
    if row.deleted_at is not None:
        raise ApiError.conflict("Задача удалена — сначала восстановите её")


async def _rows(rows: list[TasksTask], *, include_deleted: bool) -> list[TaskListRow]:
    """Задачи + их рёбра + признак ветки — в порядке дерева (больший ``sort`` выше).

    Две подмешиваемые величины берутся одним запросом каждая (``link_map_by_task_codes`` и
    ``link_child_count_by_parent_codes``), а не по запросу на карточку: список пространства
    целиком помещается на экран, и N+1 здесь стоил бы ровно столько же строк кода, сколько
    экономит.

    Порядок наводится здесь, а не в CRUD: ``task_list_by_workspace`` сортирует по важности
    (ответ на вопрос «за что взяться»), а списку нужен порядок ветки — тот, который человек
    расставил руками. Разные вопросы к одной таблице, и второй вид сортировки — это сборка
    ответа, а не другая выборка.
    """
    codes = [row.code for row in rows]
    links = await link_crud.link_map_by_task_codes(codes)
    children = await link_crud.link_child_count_by_parent_codes(
        codes, include_deleted=include_deleted
    )
    built = []
    for row in rows:
        link = links.get(row.code)
        built.append(
            TaskListRow(
                **TaskRow.model_validate(row).model_dump(),
                parent_code=link.parent_code if link else None,
                sort=link.sort if link else SORT_DEFAULT,
                has_children=children.get(row.code, 0) > 0,
            )
        )
    built.sort(key=lambda item: (-item.sort, item.created_at, item.code))
    return built


async def _detail(row: TasksTask) -> TaskDetail:
    """Задача целиком: её поля, тело, ребро, группа, родитель и дети.

    Дети удалённой задачи берутся вместе с удалёнными: мягкое удаление каскадно, и живых детей
    у задачи в корзине не осталось — показать пустой список значило бы соврать, что ветка под
    ней пуста, а человек смотрит на неё именно перед тем, как решить, восстанавливать или сносить.

    Группа и родитель тоже ищутся вместе с удалёнными: удалённая группа задачи с неё не снимается
    (см. ``group_delete``), и показать «Без группы» там, где разложенность на самом деле цела, —
    значит соврать о том, что вернётся после восстановления группы.
    """
    deleted = row.deleted_at is not None
    link = await link_crud.link_get(row.code)
    children = await task_crud.task_list_by_parent(row.code, include_deleted=deleted)
    group = (
        await group_crud.group_get(row.group_code, include_deleted=True)
        if row.group_code
        else None
    )
    parent = (
        await task_crud.task_get(link.parent_code, include_deleted=True)
        if link and link.parent_code
        else None
    )
    parent_rows = await _rows([parent], include_deleted=True) if parent else []
    stages = await stage_crud.stage_list_by_task(row.code)
    notes = await note_crud.note_list_by_task(row.code)
    return TaskDetail(
        **TaskRow.model_validate(row).model_dump(),
        context=row.context,
        constraints=row.constraints,
        criteria=row.criteria,
        body=row.body,
        parent_code=link.parent_code if link else None,
        sort=link.sort if link else SORT_DEFAULT,
        has_children=bool(children),
        group=GroupRow.model_validate(group) if group else None,
        parent=parent_rows[0] if parent_rows else None,
        children=await _rows(children, include_deleted=deleted),
        stages=[StageRow.model_validate(stage) for stage in stages],
        notes=[NoteRow.model_validate(note) for note in notes],
    )


@router.get("/tasks")
async def list_tasks(
    workspace: str = Query(..., description="Код пространства (``WORKSPACE@…`` или голый)"),
    include_deleted: bool = Query(False, description="Показать и удалённые задачи"),
    status: str | None = Query(None, description="Только задачи в этом статусе"),
    group: str | None = Query(
        None,
        description="Только задачи этой группы; пустое значение — только задачи вне групп",
    ),
) -> list[TaskListRow]:
    """Плоский список задач пространства — в нём же едут рёбра дерева.

    Плоский, потому что раскладывает его клиент: секции у него по группам, а не по уровням
    вложенности, и дерево, собранное на бэке, пришлось бы разбирать обратно. Родитель и позиция
    при этом в каждой строке — их хватает, чтобы собрать любую раскладку, включая вложенную.

    Пустое значение ``group`` — не «без фильтра», а «только вне групп»: секция «Без группы» в
    списке существует, и спросить про неё иначе нечем. «Без фильтра» — это отсутствие параметра.
    """
    bare = _code(workspace)
    await _require_workspace(bare)
    try:
        rows = await task_crud.task_list_by_workspace(
            bare,
            status=status,
            group_code=_bare(group, GROUP_CODE_PREFIX),
            include_deleted=include_deleted,
        )
    except ValueError as error:
        raise ApiError.bad_request(str(error)) from error
    return await _rows(rows, include_deleted=include_deleted)


@router.post("/tasks", status_code=201)
async def create_task(payload: TaskCreateBody) -> TaskDetail:
    """Завести задачу (вместе с её ребром дерева) и вернуть её целиком.

    Отвечаем деталью, а не строкой списка: создание из карточки родителя тут же открывает
    созданное, и второй запрос за тем, что мы только что записали, был бы лишним кругом.
    """
    try:
        row = await task_crud.task_create(
            workspace_code=_code(payload.workspace),
            title=payload.title,
            description=payload.description,
            context=payload.context,
            constraints=payload.constraints,
            criteria=payload.criteria,
            body=payload.body,
            type=payload.type,
            status=payload.status,
            priority=payload.priority,
            group_code=_bare(payload.group_code, GROUP_CODE_PREFIX),
            parent_code=_bare(payload.parent_code, TASK_CODE_PREFIX),
            deadline_at=payload.deadline_at,
        )
    except ValueError as error:
        # ValueError тут — несуществующее пространство, чужая группа, чужой родитель или значение
        # не из справочника. Всё это чинится правкой вызова, поэтому 400 с текстом CRUD (он
        # называет и допустимые значения), а не 404: искомое не «пропало», его не бывает.
        raise ApiError.bad_request(str(error)) from error
    return await _detail(row)


@router.get("/tasks/{code}")
async def get_task(code: str) -> TaskDetail:
    """Одна задача — в том числе удалённая: её состояние видно по ``deleted_at``."""
    return await _detail(await _require_task(_task_code(code)))


@router.put("/tasks/{code}")
async def update_task(code: str, payload: TaskUpdateBody) -> TaskDetail:
    """Полная замена карточки. Статус и место в дереве сюда не входят — у них свои ручки."""
    bare = _task_code(code)
    _live(await _require_task(bare))
    try:
        row = await task_crud.task_update(
            bare,
            title=payload.title,
            description=payload.description,
            context=payload.context,
            constraints=payload.constraints,
            criteria=payload.criteria,
            body=payload.body,
            type=payload.type,
            priority=payload.priority,
            # Пустая строка — единственная форма «группы нет» для CRUD: ``None`` там значит «не
            # трогать», а правка карточки обязана уметь снимать разложенность.
            group_code=_bare(payload.group_code, GROUP_CODE_PREFIX) or "",
            deadline_at=payload.deadline_at,
        )
    except ValueError as error:
        raise ApiError.bad_request(str(error)) from error
    if row is None:
        raise ApiError.not_found("Задача не найдена")
    return await _detail(row)


@router.post("/tasks/{code}/status")
async def set_task_status(code: str, payload: TaskStatusBody) -> TaskDetail:
    """Сменить статус — и вместе с ним отметку фазы (начало, завершение, отмена).

    Отдельная ручка, а не поле общей правки: отметку ставит только этот путь, и второй способ
    записать ``status`` означал бы «сделано» без даты завершения.
    """
    bare = _task_code(code)
    _live(await _require_task(bare))
    try:
        row = await task_crud.task_update_status(bare, payload.status)
    except ValueError as error:
        raise ApiError.bad_request(str(error)) from error
    if row is None:
        raise ApiError.not_found("Задача не найдена")
    return await _detail(row)


@router.post("/tasks/{code}/move")
async def move_task(code: str, payload: TaskMoveBody) -> TaskDetail:
    """Перенести задачу: новый родитель (пусто — корень) и позиция среди соседей."""
    bare = _task_code(code)
    _live(await _require_task(bare))
    try:
        link = await link_crud.link_move(
            bare,
            parent_code=_bare(payload.parent_code, TASK_CODE_PREFIX),
            sort=payload.sort,
        )
    except ValueError as error:
        # Петля в дереве, чужое пространство, несуществующий родитель — всё это неверный
        # аргумент, а не пропавшая запись.
        raise ApiError.bad_request(str(error)) from error
    if link is None:
        raise ApiError.not_found("Задача не найдена")
    return await _detail(await _require_task(bare))


@router.post("/tasks/{code}/reorder")
async def reorder_task(code: str, payload: TaskReorderBody) -> TaskDetail:
    """Перетаскивание строки списка: новое место среди соседей и, если её тянули в другую
    карточку, новая группа.

    Одно движение мышью — один запрос: смени мы группу отдельной ручкой, а порядок отдельной,
    список успел бы показать задачу в новой группе на старом месте, и человек увидел бы
    состояние, которого не просил. Порядок считается ПОСЛЕ смены группы — ряд соседей у корней
    общий на пространство, и от группы он не зависит, но сосед из тела относится уже к новой
    раскладке.

    Удалённую не двигаем: править её нельзя нигде, и порядок — то же самое правило.
    """
    bare = _task_code(code)
    _live(await _require_task(bare))
    try:
        if "group_code" in payload.model_fields_set:
            # Пустая строка — единственная форма «группы нет» для CRUD: ``None`` там значит «не
            # трогать» (см. ``task_update``).
            await task_crud.task_update(
                bare, group_code=_bare(payload.group_code, GROUP_CODE_PREFIX) or ""
            )
        row = await link_crud.link_reorder(
            bare, after_code=_bare(payload.after_code, TASK_CODE_PREFIX)
        )
    except ValueError as error:
        raise ApiError.bad_request(str(error)) from error
    if row is None:
        raise ApiError.not_found("Задача не найдена")
    return await _detail(await _require_task(bare))


@router.delete("/tasks/{code}", status_code=204)
async def delete_task(code: str) -> Response:
    """Мягкое удаление — вместе со всей веткой под задачей.

    Ветка уходит целиком потому же, почему целиком и восстанавливается: подзадача без родителя
    не работа, а осколок. Повторное удаление уже удалённой не ошибка — результат совпадает с
    желаемым.
    """
    if not await task_crud.task_delete(_task_code(code)):
        raise ApiError.not_found("Задача не найдена")
    return Response(status_code=204)


@router.post("/tasks/{code}/restore")
async def restore_task(code: str) -> TaskDetail:
    """Поднять задачу и тех потомков, что ушли вместе с ней.

    Живую восстановить нельзя: это не «уже хорошо», а признак того, что кнопку нажали не на той
    строке, и молчаливое «ок» скрыло бы расхождение экрана с базой.
    """
    bare = _task_code(code)
    existing = await _require_task(bare)
    if existing.deleted_at is None:
        raise ApiError.conflict("Задача не удалена — восстанавливать нечего")
    await task_crud.task_restore(bare)
    return await _detail(await _require_task(bare))


@router.delete("/tasks/{code}/purge", status_code=204)
async def purge_task(code: str) -> Response:
    """Физическое удаление задачи вместе со всей веткой под ней — восстанавливать будет нечего.

    Потомки перечисляются явно (это делает CRUD): каскад FK снёс бы только рёбра, а задачи-дети
    остались бы в базе вообще без места в дереве — невидимые из любого обхода.
    """
    if not await task_crud.task_delete(_task_code(code), hard=True):
        raise ApiError.not_found("Задача не найдена")
    return Response(status_code=204)


# ── этапы плана ───────────────────────────────────────────────────────────────


class StageBody(_Body):
    """Тело создания и правки этапа.

    ``number`` не обязателен: не передан — этап встаёт следующим по счёту. Явное значение нужно
    ровно для вставки в середину, и тогда хвост двигает вызывающий.

    ``evidence`` сюда входит, а ``status`` — нет: закрытие этапа проверяет доказательство, и
    делает это отдельная ручка.
    """

    title: Annotated[
        str, StringConstraints(strip_whitespace=True, min_length=1, max_length=TITLE_MAX)
    ]
    description: Annotated[
        str, StringConstraints(strip_whitespace=True, max_length=DESCRIPTION_MAX)
    ] = ""
    body: str = ""
    evidence: str = ""
    number: int | None = None


class StageStatusBody(_Body):
    """Один статус — как и у задачи."""

    status: str


def _stage_code(value: str) -> str:
    """Голый код этапа из сегмента адреса."""
    return _bare(value, STAGE_CODE_PREFIX) or ""


async def _require_stage(code: str):
    """Этап или 404."""
    row = await stage_crud.stage_get(code)
    if row is None:
        raise ApiError.not_found("Этап не найден")
    return row


@router.get("/tasks/{code}/stages")
async def list_stages(code: str) -> list[StageRow]:
    """Этапы задачи по номеру: план читается сверху вниз."""
    bare = _task_code(code)
    await _require_task(bare)
    rows = await stage_crud.stage_list_by_task(bare)
    return [StageRow.model_validate(row) for row in rows]


@router.post("/tasks/{code}/stages", status_code=201)
async def create_stage(code: str, payload: StageBody) -> StageRow:
    """Завести этап в живой задаче."""
    bare = _task_code(code)
    _live(await _require_task(bare))
    try:
        row = await stage_crud.stage_create(
            task_code=bare,
            title=payload.title,
            number=payload.number,
            description=payload.description,
            body=payload.body,
        )
    except ValueError as error:
        raise ApiError.bad_request(str(error)) from error
    return StageRow.model_validate(row)


@router.put("/stages/{code}")
async def update_stage(code: str, payload: StageBody) -> StageRow:
    """Полная замена карточки этапа. Статус сюда не входит — см. ``POST /stages/{code}/status``."""
    bare = _stage_code(code)
    await _require_stage(bare)
    try:
        row = await stage_crud.stage_update(
            bare,
            title=payload.title,
            description=payload.description,
            body=payload.body,
            number=payload.number,
            evidence=payload.evidence,
        )
    except ValueError as error:
        raise ApiError.bad_request(str(error)) from error
    if row is None:
        raise ApiError.not_found("Этап не найден")
    return StageRow.model_validate(row)


@router.post("/stages/{code}/status")
async def set_stage_status(code: str, payload: StageStatusBody) -> StageRow:
    """Сменить статус этапа.

    Закрытие требует доказательства: ``done`` с пустым ``evidence`` отвечает 400 — это и есть
    шлюз, ради которого поле заведено отдельно от описания.
    """
    bare = _stage_code(code)
    await _require_stage(bare)
    try:
        row = await stage_crud.stage_update_status(bare, payload.status)
    except TaskRuleError as error:
        # Код правила едет в ответе рядом с текстом: интерфейс показывает свою формулировку, а
        # агент читает ту же английскую фразу, что и в логах.
        raise ApiError.bad_request(str(error), code=error.code) from error
    except ValueError as error:
        raise ApiError.bad_request(str(error)) from error
    if row is None:
        raise ApiError.not_found("Этап не найден")
    return StageRow.model_validate(row)


@router.delete("/stages/{code}", status_code=204)
async def delete_stage(code: str) -> Response:
    """Снести этап. Логического удаления у него нет: брошенный этап — это статус ``canceled``."""
    if not await stage_crud.stage_delete(_stage_code(code)):
        raise ApiError.not_found("Этап не найден")
    return Response(status_code=204)


# ── журнал ────────────────────────────────────────────────────────────────────


class NoteBody(_Body):
    """Тело создания записи журнала: вид, предмет и, для факта, сразу разрешение.

    ``stage_code`` привязывает запись к этапу; без него запись относится к задаче целиком.
    """

    type: str
    title: Annotated[
        str, StringConstraints(strip_whitespace=True, min_length=1, max_length=TITLE_MAX)
    ]
    body: str = ""
    resolution: str = ""
    stage_code: str | None = None


class NoteResolutionBody(_Body):
    """Разрешение записи — то, чем она закрывается."""

    resolution: str


def _note_code(value: str) -> str:
    """Голый код записи из сегмента адреса."""
    return _bare(value, NOTE_CODE_PREFIX) or ""


@router.get("/tasks/{code}/notes")
async def list_notes(
    code: str,
    type: str | None = Query(None, description="Только записи этого вида"),
    open_only: bool = Query(False, description="Только незакрытые записи"),
) -> list[NoteRow]:
    """Журнал задачи в порядке появления."""
    bare = _task_code(code)
    await _require_task(bare)
    rows = await note_crud.note_list_by_task(bare, type=type, open_only=open_only)
    return [NoteRow.model_validate(row) for row in rows]


@router.post("/tasks/{code}/notes", status_code=201)
async def create_note(code: str, payload: NoteBody) -> NoteRow:
    """Добавить запись в журнал живой задачи."""
    bare = _task_code(code)
    _live(await _require_task(bare))
    try:
        row = await note_crud.note_create(
            task_code=bare,
            type=payload.type,
            title=payload.title,
            body=payload.body,
            stage_code=_bare(payload.stage_code, STAGE_CODE_PREFIX),
            resolution=payload.resolution,
        )
    except ValueError as error:
        raise ApiError.bad_request(str(error)) from error
    return NoteRow.model_validate(row)


@router.post("/notes/{code}/resolve")
async def resolve_note(code: str, payload: NoteResolutionBody) -> NoteRow:
    """Закрыть запись разрешением.

    Повторное закрытие отвечает 409: журнал дописываемый, и переписать разрешение задним числом
    значило бы подогнать историю под результат. Передумали — новая запись.
    """
    bare = _note_code(code)
    try:
        row = await note_crud.note_resolve(bare, payload.resolution)
    except TaskRuleError as error:
        # 409, а не 400: запись существует и в порядке — не сходится состояние, как и при правке
        # удалённой строки.
        raise ApiError.conflict(str(error), code=error.code) from error
    except ValueError as error:
        raise ApiError.bad_request(str(error)) from error
    if row is None:
        raise ApiError.not_found("Запись не найдена")
    return NoteRow.model_validate(row)


@router.delete("/notes/{code}", status_code=204)
async def delete_note(code: str) -> Response:
    """Снести запись физически — ручка человека, агенту её не отдают."""
    if not await note_crud.note_delete(_note_code(code)):
        raise ApiError.not_found("Запись не найдена")
    return Response(status_code=204)


__all__ = [
    "GroupBody",
    "NoteBody",
    "NoteResolutionBody",
    "StageBody",
    "StageStatusBody",
    "TaskCreateBody",
    "TaskMoveBody",
    "TaskStatusBody",
    "TaskUpdateBody",
    "router",
]
