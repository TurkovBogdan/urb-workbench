"""CRUD ``TasksTask`` — задачи. Каждая функция владеет своей сессией.

Три правила этого файла, которые нигде больше не продублированы:

1. **Задача и её ребро дерева рождаются вместе.** ``task_create`` пишет строку в ``tasks_link``
   в той же транзакции: без ребра задача не принадлежит дереву, а «сначала задача, потом связь»
   оставило бы окно, в котором она нигде не видна. Атомарность тут не удобство: восстановить
   потерянное ребро потом неоткуда — родителя знал только вызывающий.
2. **Согласованность пространства проверяется на записи.** Родитель и ребёнок — в одном
   пространстве, группа — из пространства задачи. Нарушение — ``ValueError`` с внятным текстом:
   схема такую связь не запрещает (FK смотрит на ``code``, а не на пару), значит запретить её
   может только этот слой.
3. **Мягкое удаление каскадно.** Удалять ветку по одной задаче бессмысленно, поэтому потомки
   получают **ту же отметку времени**, что и корень удаления. По ней же работает восстановление:
   поднимаются ровно те, чей ``deleted_at`` совпадает с отметкой родителя — задача, удалённая
   отдельно и раньше, из-под восстановления не выныривает.
"""

from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy import case, delete as sa_delete, func, or_, select, update

from src.core.database import session_scope, write_scope
from src.core.utils.date import utc_now
from src.modules.core_changes import DELETED, UPDATED, mark_changes
from src.modules.tasks.codes import new_code
from src.modules.tasks.constants import (
    ACTOR_KINDS,
    BODY_MAX,
    CONSTRAINTS_MAX,
    CONTEXT_MAX,
    CRITERIA_MAX,
    DESCRIPTION_MAX,
    STATUS_CANCELED,
    STATUS_DONE,
    STATUS_IN_PROGRESS,
    TASK_CREATED_BY_DEFAULT,
    TASK_PRIORITIES,
    TASK_PRIORITY_DEFAULT,
    TASK_PRIORITY_WEIGHTS,
    TASK_STATUS_DEFAULT,
    TASK_STATUSES,
    TASK_STATUSES_TERMINAL,
    TASK_TYPE_DEFAULT,
    TASK_TYPES,
    TITLE_MAX,
)
from src.modules.tasks.crud.link import (
    bottom_sort,
    link_move_in,
    link_reorder_in,
    require_open_parent,
    require_parent_group_alive,
    require_root_parent,
)
from src.modules.tasks.models.group import TasksGroup
from src.modules.tasks.models.link import TasksLink
from src.modules.tasks.models.note import TasksNote
from src.modules.tasks.models.stage import TasksStage
from src.modules.tasks.models.task import TasksTask
from src.modules.tasks.text import clip, fit
from src.modules.workspace.models.workspace import Workspace

# Приоритет сортируется по весу, а не по слову: алфавит про важность ничего не знает
# (``burning`` встал бы между ``agent`` и ``frozen`` без всякого смысла). Неизвестное значение
# уезжает в самый низ — CHECK его не пропустит, но выражение обязано быть тотальным.
_PRIORITY_ORDER = case(
    TASK_PRIORITY_WEIGHTS,
    value=TasksTask.priority,
    else_=max(TASK_PRIORITY_WEIGHTS.values()) + 10,
)


class _Keep:
    """Метка «поле не передано» для ``task_update``.

    Нужна только датам. У текста «не передано» выражается через ``None`` (пустую строку колонка
    хранит сама), у ссылки на группу — через ``""`` (см. ``task_update``), а у даты свободного
    значения не остаётся: и «не трогать», и «стереть срок» — это один и тот же ``None``.
    Разводить их приходится отдельным объектом, иначе снять однажды поставленный срок было бы
    нечем, и правка карточки умела бы только добавлять.
    """

    __slots__ = ()

    def __repr__(self) -> str:  # pragma: no cover — только для отладочного вывода
        return "KEEP"


KEEP = _Keep()

# Отметка фазы, которую ставит переход в статус. Остальные статусы фаз не отмечают: «в тесте» и
# «на ревью» — это всё ещё «работа идёт», а второй записи о её начале не нужно.
_STATUS_STAMPS = {
    STATUS_IN_PROGRESS: "started_at",
    STATUS_DONE: "completed_at",
    STATUS_CANCELED: "canceled_at",
}


def _checked(value: str, allowed: tuple[str, ...], field: str) -> str:
    """Значение из справочника или отказ со списком допустимых.

    Дублирует ``CHECK`` в схеме намеренно: из базы то же нарушение прилетело бы
    ``IntegrityError`` с именем констрейнта — текстом для инженера, а не для вызывающего.
    """
    if value not in allowed:
        raise ValueError(
            f"Unknown {field} {value!r}. Allowed: {', '.join(allowed)}."
        )
    return value


def _hit(query: str, *fields: str | None) -> bool:
    """Подстрока без учёта регистра — сравнение в Python, а не в SQL.

    ``lower()`` в SQLite складывает только ASCII: запрос «Панель» не нашёл бы «панель», зато на
    PostgreSQL нашёл бы — один и тот же поиск отвечал бы по-разному на двух провайдерах, и
    разошлись бы они молча. Строк в выборке сотни, а не сотни тысяч, поэтому цена отбора на
    стороне приложения — ничто рядом с этой разницей.
    """
    needle = query.lower()
    return any(field and needle in field.lower() for field in fields)


async def _require_workspace(s, workspace_code: str) -> None:
    stmt = select(Workspace.code).where(
        Workspace.code == workspace_code, Workspace.deleted_at.is_(None)
    )
    if (await s.execute(stmt)).scalar_one_or_none() is None:
        raise ValueError(
            f"Workspace {workspace_code!r} does not exist (or is deleted) — "
            "a task always belongs to a live workspace."
        )


async def _require_group_of(s, group_code: str, workspace_code: str) -> None:
    """Группа существует и принадлежит тому же пространству, что и задача."""
    stmt = select(TasksGroup.workspace_code).where(
        TasksGroup.code == group_code, TasksGroup.deleted_at.is_(None)
    )
    owner = (await s.execute(stmt)).scalar_one_or_none()
    if owner is None:
        raise ValueError(f"Group {group_code!r} does not exist (or is deleted).")
    if owner != workspace_code:
        raise ValueError(
            f"Group {group_code!r} belongs to workspace {owner!r}, but the task belongs to "
            f"{workspace_code!r} — a group never spans workspaces."
        )


async def _require_parent_of(
    s, parent_code: str, workspace_code: str, child_status: str
) -> str | None:
    """Родитель существует, живёт в том же пространстве, что и ребёнок, открыт для него и сам
    не подзадача.

    Ответ — группа родителя: ребёнок получает её вместе с местом в дереве.
    """
    stmt = select(TasksTask.workspace_code, TasksTask.group_code, TasksTask.status).where(
        TasksTask.code == parent_code, TasksTask.deleted_at.is_(None)
    )
    found = (await s.execute(stmt)).one_or_none()
    if found is None:
        raise ValueError(f"Parent task {parent_code!r} does not exist (or is deleted).")
    owner, parent_group, parent_status = found
    if owner != workspace_code:
        raise ValueError(
            f"Parent task {parent_code!r} belongs to workspace {owner!r}, but the child "
            f"belongs to {workspace_code!r} — a branch never spans workspaces."
        )
    require_open_parent(parent_code, parent_status, child_status)
    await require_parent_group_alive(s, parent_code, parent_group)
    await require_root_parent(s, parent_code)
    return parent_group


async def _require_parent_group(s, code: str, group_code: str | None) -> None:
    """Отказ, если подзадаче назначают группу не её родителя.

    Корня это не касается. Подзадаче разрешена ровно одна группа — родительская: так её можно
    вернуть туда, если она разошлась с родителем до того, как правило появилось.
    """
    link = await s.get(TasksLink, code)
    if link is None or link.parent_code is None:
        return
    parent = await s.get(TasksTask, link.parent_code)
    if parent is None or parent.group_code == group_code:
        return
    raise ValueError(
        f"Task {code!r} is a subtask of {link.parent_code!r}, and a subtask sits in its "
        f"parent's group. File {link.parent_code!r} instead — its subtasks follow it — or take "
        f"{code!r} out of the branch first."
    )


async def _carry_children(s, parent: TasksTask) -> None:
    """Подзадачи следуют за родителем в его новую группу — удалённые тоже.

    Удалённые — потому что восстановление поднимает их на прежнее место в дереве, и с чужой
    группой они вернулись бы нарушением, которое никто не совершал.
    """
    children = list(
        (
            await s.execute(
                select(TasksLink.task_code).where(TasksLink.parent_code == parent.code)
            )
        )
        .scalars()
        .all()
    )
    if not children:
        return
    await s.execute(
        update(TasksTask)
        .where(TasksTask.code.in_(children))
        .values(group_code=parent.group_code, updated_at=utc_now())
    )
    mark_changes(s, "tasks.task", UPDATED, children)


async def _branch_stamp(s, branch: list[str]) -> datetime:
    """Отметка удаления, которой в этой ветке ещё никто не помечен.

    Отметка — идентификатор операции удаления (по ней восстановление отбирает «ушедших вместе»),
    а точность у неё секундная: ``utc_now`` режет микросекунды, и ``TIMESTAMP(precision=0)`` на
    PostgreSQL тоже. Удалить потомка отдельно и через мгновение — родителя целиком это ровно
    одна секунда, и две разные операции получили бы одну отметку: восстановление родителя
    подняло бы заодно и то, что человек убрал раньше и намеренно. Поэтому при совпадении
    отметка сдвигается на секунду вперёд — чужой операции она уже не принадлежит.
    """
    stmt = select(TasksTask.deleted_at).where(
        TasksTask.code.in_(branch), TasksTask.deleted_at.is_not(None)
    )
    taken = set((await s.execute(stmt)).scalars().all())
    stamp = utc_now()
    while stamp in taken:
        stamp += timedelta(seconds=1)
    return stamp


async def _descendant_codes(s, code: str) -> list[str]:
    """Коды всех потомков задачи — обход дерева вширь по таблице связей.

    Обход в Python, а не рекурсивный CTE: дерево задач одного разработчика измеряется сотнями
    строк, а читаемость выражения тут дороже одного round-trip. ``seen`` защищает от цикла,
    который в базу мог попасть мимо CRUD: вечный цикл в удалении хуже кривого дерева.
    """
    found: list[str] = []
    seen = {code}
    frontier = [code]
    while frontier:
        stmt = select(TasksLink.task_code).where(TasksLink.parent_code.in_(frontier))
        children = [c for c in (await s.execute(stmt)).scalars().all() if c not in seen]
        seen.update(children)
        found.extend(children)
        frontier = children
    return found


async def task_create(
    *,
    workspace_code: str,
    title: str,
    group_code: str | None = None,
    parent_code: str | None = None,
    description: str | None = None,
    context: str | None = None,
    constraints: str | None = None,
    criteria: str | None = None,
    body: str | None = None,
    type: str = TASK_TYPE_DEFAULT,
    status: str = TASK_STATUS_DEFAULT,
    priority: str = TASK_PRIORITY_DEFAULT,
    created_by: str = TASK_CREATED_BY_DEFAULT,
    deadline_at: datetime | None = None,
) -> TasksTask:
    """Завести задачу вместе с её ребром дерева.

    ``parent_code=None`` — корень пространства. Ребро всегда создаётся с
    позицией под всем рядом соседей (``bottom_sort``): расстановка наверху — работа рук, и свежая
    задача не должна прыгать через неё. Дальше её двигают перетаскиванием (``link_reorder``) или
    переносят под другого родителя (``task_update(parent_code=…)``).

    Подзадача получает группу родителя. Пустая ``group_code`` — «не задано», а не «вне группы»:
    так форма, которая про группу подзадачи ничего не спрашивает, не упирается в отказ.
    """
    _checked(type, TASK_TYPES, "task type")
    _checked(status, TASK_STATUSES, "task status")
    _checked(priority, TASK_PRIORITIES, "task priority")
    _checked(created_by, ACTOR_KINDS, "actor kind")
    async with write_scope() as s:
        await _require_workspace(s, workspace_code)
        if group_code:
            await _require_group_of(s, group_code, workspace_code)
        if parent_code:
            parent_group = await _require_parent_of(s, parent_code, workspace_code, status)
            if group_code and group_code != parent_group:
                parent_filing = f"under {parent_group!r}" if parent_group else "in no group"
                raise ValueError(
                    f"A subtask sits in its parent's group, and {parent_code!r} is filed "
                    f"{parent_filing}, not under {group_code!r}. Leave the group out — the "
                    "subtask takes its parent's."
                )
            group_code = parent_group
        row = TasksTask(
            code=new_code(),
            workspace_code=workspace_code,
            group_code=group_code or None,
            type=type,
            status=status,
            priority=priority,
            title=clip(title, TITLE_MAX),
            description=clip(description, DESCRIPTION_MAX),
            context=clip(context, CONTEXT_MAX),
            constraints=clip(constraints, CONSTRAINTS_MAX),
            criteria=clip(criteria, CRITERIA_MAX),
            body=fit(body, BODY_MAX, "task body"),
            deadline_at=deadline_at,
            created_by=created_by,
        )
        s.add(row)
        await s.flush()
        s.add(
            TasksLink(
                task_code=row.code,
                parent_code=parent_code or None,
                # Под всем рядом соседей, а не в постоянные 500: ряд, переставленный мышью,
                # перенумерован от своей длины, и постоянное значение вклинивало бы свежую
                # задачу в его середину.
                sort=await bottom_sort(
                    s, parent_code or None, workspace_code, group_code or None
                ),
            )
        )
        await s.flush()
        await s.refresh(row)
    return row


async def task_get(code: str, *, include_deleted: bool = False) -> TasksTask | None:
    stmt = select(TasksTask).where(TasksTask.code == code)
    if not include_deleted:
        stmt = stmt.where(TasksTask.deleted_at.is_(None))
    async with session_scope() as s:
        return (await s.execute(stmt)).scalar_one_or_none()


async def task_list_by_workspace(
    workspace_code: str,
    *,
    status: str | None = None,
    statuses: tuple[str, ...] | None = None,
    query: str | None = None,
    group_code: str | None = None,
    include_deleted: bool = False,
) -> list[TasksTask]:
    """Плоский список задач пространства в РУЧНОМ порядке: больший ``sort`` выше.

    Порядок задаёт человек перетаскиванием (``link_reorder``), и он же — единственная правда о
    том, что за чем идёт. Раньше список строился по важности и времени появления; с ручной
    расстановкой это несовместимо: строка, переставленная мышью, возвращалась бы на своё место
    следующим же запросом. Важность осталась глифом в строке и фильтром над ней.

    Сортировка живёт в ``tasks_link`` — её значения у детей одного родителя свои, и общий список
    (корни вперемешку с ветками) порядок внутри каждой ветки сохраняет: интерфейс всё равно
    раскладывает плоский ответ по родителям.

    ``group_code=""`` — только неразложенные (единственная форма спросить про ``NULL``), код —
    только эта группа, ``None`` — не фильтровать по группе вовсе.

    ``status`` сужает до одного значения, ``statuses`` — до набора (так выражается «всё
    незавершённое»: перечислить пять статусов дешевле, чем заводить в схеме отрицание). Заданы
    оба — применяются оба, то есть пересечение; звать так незачем, но и запрещать нечего.

    ``query`` ищет подстроку без учёта регистра в заголовке и цели. Тела сюда не входят: по ним
    ищут отдельно и по явной просьбе — ``task_search_codes``.
    """
    stmt = (
        select(TasksTask)
        .join(TasksLink, TasksLink.task_code == TasksTask.code)
        .where(TasksTask.workspace_code == workspace_code)
        .order_by(TasksLink.sort.desc(), TasksTask.created_at.asc(), TasksTask.code.asc())
    )
    if status is not None:
        stmt = stmt.where(TasksTask.status == _checked(status, TASK_STATUSES, "task status"))
    if statuses is not None:
        for value in statuses:
            _checked(value, TASK_STATUSES, "task status")
        stmt = stmt.where(TasksTask.status.in_(statuses))
    if group_code == "":
        stmt = stmt.where(TasksTask.group_code.is_(None))
    elif group_code is not None:
        stmt = stmt.where(TasksTask.group_code == group_code)
    if not include_deleted:
        stmt = stmt.where(TasksTask.deleted_at.is_(None))
    async with session_scope() as s:
        rows = list((await s.execute(stmt)).scalars().all())
    if not query:
        return rows
    return [row for row in rows if _hit(query, row.title, row.description)]


async def task_search_codes(
    workspace_code: str,
    query: str,
    *,
    in_brief: bool = False,
    in_plan: bool = False,
    in_journal: bool = False,
) -> list[str]:
    """Коды задач пространства, у которых запрос нашёлся В ТЕЛАХ — по названным областям.

    Заголовка и цели здесь нет намеренно: их видно в строке списка, и ищет по ним тот, у кого
    список уже на руках. Сюда ходят за тем, чего в строке нет, — за постановкой, планом с
    этапами и журналом. Ни одна область не включена по умолчанию: поиск, тихо залезающий в
    восьмикилобайтные тела, возвращает совпадения, по которым не понять, та ли это задача.

    Отдаются ИМЕННО коды, а не строки: спрашивающий держит список пространства целиком и
    пересекает его со своим — второй копии тех же карточек ему не нужно. По той же причине
    удалённые не отсеиваются: что показывать, решает пересечение на той стороне.
    """
    if not query or not (in_brief or in_plan or in_journal):
        return []

    hits: set[str] = set()

    if in_brief or in_plan:
        columns = [TasksTask.code]
        if in_brief:
            columns += [TasksTask.context, TasksTask.constraints, TasksTask.criteria]
        if in_plan:
            columns.append(TasksTask.body)
        stmt = select(*columns).where(TasksTask.workspace_code == workspace_code)
        async with session_scope() as s:
            for code, *texts in (await s.execute(stmt)).all():
                if _hit(query, *texts):
                    hits.add(code)

    # Этапы и журнал висят на задаче и своего пространства не знают — отсюда join к задаче.
    if in_plan:
        stmt = (
            select(
                TasksStage.task_code,
                TasksStage.title,
                TasksStage.description,
                TasksStage.body,
                TasksStage.evidence,
            )
            .join(TasksTask, TasksTask.code == TasksStage.task_code)
            .where(TasksTask.workspace_code == workspace_code)
        )
        async with session_scope() as s:
            for task_code, *texts in (await s.execute(stmt)).all():
                if _hit(query, *texts):
                    hits.add(task_code)

    if in_journal:
        stmt = (
            select(TasksNote.task_code, TasksNote.title, TasksNote.body, TasksNote.resolution)
            .join(TasksTask, TasksTask.code == TasksNote.task_code)
            .where(TasksTask.workspace_code == workspace_code)
        )
        async with session_scope() as s:
            for task_code, *texts in (await s.execute(stmt)).all():
                if _hit(query, *texts):
                    hits.add(task_code)

    return sorted(hits)


async def task_list_by_parent(
    parent_code: str | None,
    *,
    workspace_code: str | None = None,
    include_deleted: bool = False,
) -> list[TasksTask]:
    """Дети узла по порядку (больший ``sort`` выше).

    ``parent_code=None`` — корни; корней у каждого пространства свои, поэтому вместе с ``None``
    осмысленно передать ``workspace_code``, иначе в ответ приедут корни всех пространств сразу.
    """
    stmt = (
        select(TasksTask)
        .join(TasksLink, TasksLink.task_code == TasksTask.code)
        .order_by(TasksLink.sort.desc(), TasksTask.code.asc())
    )
    if parent_code is None:
        stmt = stmt.where(TasksLink.parent_code.is_(None))
    else:
        stmt = stmt.where(TasksLink.parent_code == parent_code)
    if workspace_code is not None:
        stmt = stmt.where(TasksTask.workspace_code == workspace_code)
    if not include_deleted:
        stmt = stmt.where(TasksTask.deleted_at.is_(None))
    async with session_scope() as s:
        return list((await s.execute(stmt)).scalars().all())


async def _refile(s, row: TasksTask) -> None:
    """Задача сменила группу — положить её в конец ряда новой.

    Ряд соседей у корня — это его группа (``crud/link.py::_siblings``), поэтому переезд между
    группами это переезд между рядами: прежнее число позиции в новом ряду не значит ничего, и
    оставить его — значит воткнуть задачу в середину чужой расстановки наугад. В конец, а не в
    начало, по той же причине, что и у свежей задачи: верх ряда — работа рук.

    Подзадачу не трогаем: её ряд задан родителем, и смена группы на место в дереве не влияет.
    """
    link = await s.get(TasksLink, row.code)
    if link is None or link.parent_code is not None:
        return
    link.sort = await bottom_sort(
        s, None, row.workspace_code, row.group_code, moved_code=row.code
    )


async def _place_in_tree(
    s, row: TasksTask, *, parent_code: str | None, group_code: str | None
) -> None:
    """Родитель, затем группа — внутри транзакции вызывающего; ``None`` — не трогать.

    Группа после родителя: так «вынести в корень и сразу в другую группу» — одно движение, а
    группа подзадачи проверяется уже на её новом месте.
    """
    if group_code:
        await _require_group_of(s, group_code, row.workspace_code)
    if parent_code is not None:
        link = await s.get(TasksLink, row.code)
        if link is not None and (parent_code or None) != link.parent_code:
            await link_move_in(s, row, parent_code)
    if group_code is None or (group_code or None) == row.group_code:
        return
    if parent_code:
        raise ValueError(
            f"Moving {row.code!r} under {parent_code!r} gives it {parent_code!r}'s group — "
            "a subtask sits in its parent's group. Leave group_code out, or pass the parent's."
        )
    await _require_parent_group(s, row.code, group_code or None)
    row.group_code = group_code or None
    await _refile(s, row)
    await _carry_children(s, row)


async def task_reorder(
    code: str,
    *,
    after_code: str | None,
    parent_code: str | None = None,
    group_code: str | None = None,
) -> TasksTask | None:
    """Перетаскивание строки: новое место в дереве и в ряду — одной транзакцией.

    ``parent_code`` / ``group_code`` — как у ``task_update`` (``None`` — не трогать, ``""`` —
    снять), ``after_code`` — сосед сверху в новом ряду, ``None`` — в начало. Отказ позиции
    откатывает и перенос: иначе человек видел бы ошибку, а задача уже стояла бы на новом месте.
    ``None`` в ответе — задачи нет (или она удалена).
    """
    async with write_scope() as s:
        row = await s.get(TasksTask, code)
        if row is None or row.deleted_at is not None:
            return None
        await _place_in_tree(s, row, parent_code=parent_code, group_code=group_code)
        await link_reorder_in(s, code, after_code=after_code)
        await s.flush()
        await s.refresh(row)
    return row


async def task_update(
    code: str,
    *,
    title: str | None = None,
    description: str | None = None,
    context: str | None = None,
    constraints: str | None = None,
    criteria: str | None = None,
    body: str | None = None,
    type: str | None = None,
    priority: str | None = None,
    group_code: str | None = None,
    parent_code: str | None = None,
    deadline_at: datetime | None | _Keep = KEEP,
) -> TasksTask | None:
    """Обновить переданные поля задачи (``None`` = не трогать).

    ``group_code=""`` — снять разложенность (``NULL``): пустая строка означает «не задано» во всех
    текстовых полях модуля, а для ссылки единственная форма «не задано» — ``NULL``.

    ``parent_code`` — перенести под этого родителя, ``""`` — вынести в корень; правила переноса —
    ``crud/link.py::link_move_in``. Перенос и правка карточки — одна транзакция: отказ переноса
    откатывает и правку. Группа применяется после переноса, поэтому «вынести в корень и сразу в
    другую группу» — один вызов, а группа подзадачи — только родительская. Сменившему группу
    корню подзадачи следуют.

    У дат «не трогать» — это ``KEEP``, а ``None`` стирает дату: дата — единственное поле, у
    которого нет своего «пустого» значения помимо ``None`` (см. ``_Keep``).

    Статуса здесь нет намеренно: его меняет ``task_update_status``, потому что переход ставит
    ещё и отметку фазы, и разрешать обойти её стороной незачем.
    """
    if type is not None:
        _checked(type, TASK_TYPES, "task type")
    if priority is not None:
        _checked(priority, TASK_PRIORITIES, "task priority")
    async with write_scope() as s:
        row = await s.get(TasksTask, code)
        if row is None or row.deleted_at is not None:
            return None
        if title is not None:
            row.title = clip(title, TITLE_MAX)
        if description is not None:
            row.description = clip(description, DESCRIPTION_MAX)
        if context is not None:
            row.context = clip(context, CONTEXT_MAX)
        if constraints is not None:
            row.constraints = clip(constraints, CONSTRAINTS_MAX)
        if criteria is not None:
            row.criteria = clip(criteria, CRITERIA_MAX)
        if body is not None:
            row.body = fit(body, BODY_MAX, "task body")
        if type is not None:
            row.type = type
        if priority is not None:
            row.priority = priority
        await _place_in_tree(s, row, parent_code=parent_code, group_code=group_code)
        if not isinstance(deadline_at, _Keep):
            row.deadline_at = deadline_at
        await s.flush()
        await s.refresh(row)
    return row


async def _require_no_open_subtasks(s, row: TasksTask, status: str) -> None:
    """Отказ закрыть задачу, пока у неё есть незакрытые живые подзадачи — они названы."""
    open_subtasks_query = (
        select(TasksTask.code, TasksTask.status)
        .join(TasksLink, TasksLink.task_code == TasksTask.code)
        .where(
            TasksLink.parent_code == row.code,
            TasksTask.deleted_at.is_(None),
            TasksTask.status.not_in(TASK_STATUSES_TERMINAL),
        )
    )
    open_subtasks = (await s.execute(open_subtasks_query)).all()
    if open_subtasks:
        named = ", ".join(f"{code!r} ({state})" for code, state in open_subtasks)
        raise ValueError(
            f"Task {row.code!r} cannot be {status!r} while its subtasks are open: {named}. "
            "Close or cancel them first, or take them out of this task."
        )


async def _require_open_parent_for_status(s, row: TasksTask, status: str) -> None:
    """Отказ открыть подзадачу закрытой задачи: сначала переоткрывают родителя."""
    link = await s.get(TasksLink, row.code)
    if link is None or link.parent_code is None:
        return
    parent = await s.get(TasksTask, link.parent_code)
    if parent is None or parent.status not in TASK_STATUSES_TERMINAL:
        return
    raise ValueError(
        f"Task {row.code!r} is a subtask of {link.parent_code!r}, which is {parent.status!r} — "
        f"a closed task holds no open parts, so {row.code!r} cannot go to {status!r}. Reopening "
        f"{link.parent_code!r} is the person's call; ask for it."
    )


async def task_update_status(code: str, status: str) -> TasksTask | None:
    """Сменить статус и отметить фазу: ``in_progress`` → ``started_at``, ``done`` →
    ``completed_at``, ``canceled`` → ``canceled_at``.

    Отметка ставится только в первый раз: возврат из ``done`` в работу и обратно не должен
    переписывать дату, когда за задачу сели, — это факт, а не текущее состояние.

    Закрытая задача не держит открытых частей — с обеих сторон: задачу с незакрытыми живыми
    подзадачами не закрывают, а подзадачу закрытой задачи не открывают. Что при этом делать с
    родителем, решает человек — переоткрыть его или закрыть части, — поэтому здесь отказ, а не
    каскад.
    """
    _checked(status, TASK_STATUSES, "task status")
    async with write_scope() as s:
        row = await s.get(TasksTask, code)
        if row is None or row.deleted_at is not None:
            return None
        closing = status in TASK_STATUSES_TERMINAL
        if closing:
            await _require_no_open_subtasks(s, row, status)
        else:
            await _require_open_parent_for_status(s, row, status)
        row.status = status
        stamp_field = _STATUS_STAMPS.get(status)
        if stamp_field is not None and getattr(row, stamp_field) is None:
            setattr(row, stamp_field, utc_now())
        await s.flush()
        await s.refresh(row)
    return row


async def task_delete(code: str, *, hard: bool = False) -> bool:
    """Удалить задачу вместе с веткой. ``True`` — задача существовала.

    Мягкий путь (по умолчанию) ставит **одну и ту же** отметку времени задаче и всем её потомкам
    — по ней потом работает ``task_restore``. Уже удалённые ранее потомки свою отметку
    сохраняют и из-под восстановления не поднимутся (как это держится при секундной точности
    времени — см. ``_branch_stamp``).

    ``hard=True`` физически сносит всю ветку. Потомков приходится перечислять явно: FK-каскад
    снёс бы только рёбра (``tasks_link``), а сами задачи-потомки остались бы в базе вообще без
    места в дереве — невидимые ни из одного обхода.
    """
    async with write_scope() as s:
        row = await s.get(TasksTask, code)
        if row is None:
            return False
        branch = [code, *await _descendant_codes(s, code)]
        if hard:
            await s.execute(
                sa_delete(TasksLink).where(
                    or_(
                        TasksLink.task_code.in_(branch),
                        TasksLink.parent_code.in_(branch),
                    )
                )
            )
            await s.execute(sa_delete(TasksTask).where(TasksTask.code.in_(branch)))
            # Массовые операторы объектов не дают — ленте изменений ветку называем сами.
            mark_changes(s, "tasks.task", DELETED, branch)
            mark_changes(s, "tasks.link", DELETED, branch)
        else:
            stamp = await _branch_stamp(s, branch)
            await s.execute(
                update(TasksTask)
                .where(TasksTask.code.in_(branch), TasksTask.deleted_at.is_(None))
                .values(deleted_at=stamp)
            )
            # Мягкое удаление — правка строки (отметка ``deleted_at``), а не исчезновение.
            mark_changes(s, "tasks.task", UPDATED, branch)
    return True


async def task_restore(code: str) -> bool:
    """Поднять задачу и тех потомков, что ушли вместе с ней. ``True`` — задача была удалена.

    Признак «ушли вместе» — совпадение ``deleted_at`` с отметкой самой задачи: другой отметкой
    помечено отдельное, более раннее удаление, и воскрешать его никто не просил.
    """
    async with write_scope() as s:
        row = await s.get(TasksTask, code)
        if row is None or row.deleted_at is None:
            return False
        stamp = row.deleted_at
        branch = [code, *await _descendant_codes(s, code)]
        await s.execute(
            update(TasksTask)
            .where(TasksTask.code.in_(branch), TasksTask.deleted_at == stamp)
            .values(deleted_at=None)
        )
        mark_changes(s, "tasks.task", UPDATED, branch)
    return True


async def task_count_by_workspace_codes(
    workspace_codes: list[str], *, include_deleted: bool = False
) -> dict[str, int]:
    """``workspace_code → сколько в нём задач`` одним ``GROUP BY`` — для списка пространств.

    Счётчики всех карточек списка берутся одним запросом, а не по запросу на карточку: список
    целиком помещается на экран, и N+1 здесь стоил бы ровно столько же строк кода, сколько
    экономит. Пространства без задач в ответе просто нет — ноль подставляет вызывающий.
    """
    if not workspace_codes:
        return {}
    stmt = (
        select(TasksTask.workspace_code, func.count())
        .where(TasksTask.workspace_code.in_(workspace_codes))
        .group_by(TasksTask.workspace_code)
    )
    if not include_deleted:
        stmt = stmt.where(TasksTask.deleted_at.is_(None))
    async with session_scope() as s:
        return {code: count for code, count in (await s.execute(stmt)).all()}


async def task_count_by_group_codes(
    group_codes: list[str], *, include_deleted: bool = False
) -> dict[str, int]:
    """``group_code → сколько в ней задач`` одним ``GROUP BY`` — для списка групп.

    Тем же приёмом, что и счётчик по пространствам: список групп помещается на экран целиком, и
    запрос на карточку дал бы N+1 там, где хватает одной группировки. Группы без задач в ответе
    нет — ноль подставляет вызывающий.
    """
    if not group_codes:
        return {}
    stmt = (
        select(TasksTask.group_code, func.count())
        .where(TasksTask.group_code.in_(group_codes))
        .group_by(TasksTask.group_code)
    )
    if not include_deleted:
        stmt = stmt.where(TasksTask.deleted_at.is_(None))
    async with session_scope() as s:
        return {code: count for code, count in (await s.execute(stmt)).all()}


async def task_workspace_by_codes(codes: list[str]) -> dict[str, str]:
    """``code → workspace_code`` для живых задач одним запросом; пропавших в ответе нет.

    Нужна тому, кто проверяет контур у ПАЧКИ кодов: забор (``mcp/scope.py``) читает по одной
    задаче за раз, и на списке это превратилось бы в запрос на элемент. Отсутствие кода в ответе
    — это и «нет такой», и «удалена»: для проверки перед записью разницы между ними нет.
    """
    if not codes:
        return {}
    stmt = select(TasksTask.code, TasksTask.workspace_code).where(
        TasksTask.code.in_(codes), TasksTask.deleted_at.is_(None)
    )
    async with session_scope() as s:
        return {code: workspace for code, workspace in (await s.execute(stmt)).all()}


async def task_regroup(codes: list[str], group_code: str | None) -> int:
    """Переложить пачку задач в группу (``None`` — снять разложенность); вернуть, сколько легло.

    Одна транзакция на всю пачку, и это её причина существовать: та же работа тремя вызовами
    ``task_update`` даёт частичное применение, а частично переложенная пачка выглядит ровно как
    переложенная.

    Поэтому и проверки идут до первой записи: пропавшая задача, задачи из разных пространств,
    группа не оттуда — всё это ``ValueError`` с перечислением виноватых кодов, и ни одна строка
    при этом не тронута.

    Группа подзадачи — группа её родителя, поэтому подзадачи переложенного корня едут за ним, а
    подзадача в пачке без своего родителя — отказ (кроме той, что возвращается в его группу).

    Строки правятся через ORM, а не массовым ``UPDATE``: ``onupdate`` у ``updated_at`` висит на
    маппере, и в обход него отметка времени осталась бы вчерашней.
    """
    if not codes:
        raise ValueError("No task codes given — name at least one task to file.")
    async with write_scope() as s:
        rows = list(
            (
                await s.execute(
                    select(TasksTask).where(
                        TasksTask.code.in_(codes), TasksTask.deleted_at.is_(None)
                    )
                )
            )
            .scalars()
            .all()
        )
        missing = [code for code in codes if code not in {row.code for row in rows}]
        if missing:
            raise ValueError(
                f"No live task for {', '.join(repr(code) for code in missing)} — "
                "nothing was filed."
            )
        workspaces = {row.workspace_code for row in rows}
        if len(workspaces) > 1:
            raise ValueError(
                "These tasks live in different workspaces "
                f"({', '.join(sorted(repr(code) for code in workspaces))}) — "
                "a single call files work inside one."
            )
        if group_code:
            await _require_group_of(s, group_code, workspaces.pop())
        target = group_code or None
        parent_by_subtask = dict(
            (
                await s.execute(
                    select(TasksLink.task_code, TasksLink.parent_code).where(
                        TasksLink.task_code.in_(codes), TasksLink.parent_code.is_not(None)
                    )
                )
            ).all()
        )
        parent_groups = dict(
            (
                await s.execute(
                    select(TasksTask.code, TasksTask.group_code).where(
                        TasksTask.code.in_(set(parent_by_subtask.values()))
                    )
                )
            ).all()
        )
        # Подзадача, чей родитель едет в той же пачке, уедет за ним сама — отказывать ей не за что.
        misfiled = [
            code
            for code, parent in parent_by_subtask.items()
            if parent not in codes and parent_groups.get(parent) != target
        ]
        if misfiled:
            named = ", ".join(
                f"{code!r} (a subtask of {parent_by_subtask[code]!r})" for code in misfiled
            )
            raise ValueError(
                f"{named} — a subtask sits in its parent's group. File the parents instead, "
                "their subtasks follow them. Nothing was filed."
            )
        # Переложенные встают в конец ряда новой группы — по одной, в порядке перечисления:
        # ряд у корня и есть группа, и прежняя позиция в другой группе к новой не относится.
        for row in rows:
            if target == row.group_code:
                continue
            row.group_code = target
            await _refile(s, row)
            await _carry_children(s, row)
        await s.flush()
    return len(rows)


__all__ = [
    "KEEP",
    "task_count_by_group_codes",
    "task_count_by_workspace_codes",
    "task_create",
    "task_delete",
    "task_get",
    "task_list_by_parent",
    "task_list_by_workspace",
    "task_regroup",
    "task_reorder",
    "task_restore",
    "task_update",
    "task_update_status",
    "task_workspace_by_codes",
]
