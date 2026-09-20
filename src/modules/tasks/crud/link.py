"""CRUD ``TasksLink`` — рёбра дерева задач. Каждая функция владеет своей сессией.

Строку связи создаёт ``task_create`` (вместе с задачей), удаляет её каскад FK — поэтому здесь
нет ни ``link_create``, ни ``link_delete``: ребро не живёт отдельно от задачи. Остаются операции
над формой дерева — перенос ветки и её расстановка среди соседей.

Логического удаления у ребра нет: «удалена» бывает задача, а её ребро просто едет следом
(``include_deleted`` тут поэтому не параметр — фильтровать нечего).
"""

from __future__ import annotations

from sqlalchemy import func, select

from src.core.database import session_scope, write_scope
from src.modules.tasks.constants import SORT_DEFAULT, SORT_STEP
from src.modules.tasks.models.link import TasksLink
from src.modules.tasks.models.task import TasksTask


async def _workspace_of(s, task_code: str) -> str | None:
    """Пространство задачи (``None`` — задачи нет)."""
    stmt = select(TasksTask.workspace_code).where(TasksTask.code == task_code)
    return (await s.execute(stmt)).scalar_one_or_none()


async def _descendants(s, code: str) -> set[str]:
    """Коды потомков — обход вширь; нужен только для проверки на петлю при переносе."""
    seen = {code}
    frontier = [code]
    while frontier:
        stmt = select(TasksLink.task_code).where(TasksLink.parent_code.in_(frontier))
        children = [c for c in (await s.execute(stmt)).scalars().all() if c not in seen]
        seen.update(children)
        frontier = children
    return seen - {code}


async def _next_sort(
    s, parent_code: str | None, workspace_code: str, *, moved_code: str
) -> int:
    """Позиция в конце списка соседей: ``max(sort) + SORT_STEP``, а на пустом месте — ``SORT_DEFAULT``.

    Соседи считаются в пределах пространства: у корней (``parent_code IS NULL``) общего родителя
    нет, и без этого условия в максимум попали бы корни чужих пространств. Сама переезжающая
    задача из соседей исключена — иначе перестановка внутри того же списка всё время двигала бы
    её относительно собственной прежней позиции.
    """
    stmt = (
        select(func.max(TasksLink.sort))
        .join(TasksTask, TasksTask.code == TasksLink.task_code)
        .where(
            TasksTask.workspace_code == workspace_code,
            TasksLink.task_code != moved_code,
        )
    )
    if parent_code is None:
        stmt = stmt.where(TasksLink.parent_code.is_(None))
    else:
        stmt = stmt.where(TasksLink.parent_code == parent_code)
    top = (await s.execute(stmt)).scalar_one_or_none()
    return SORT_DEFAULT if top is None else top + SORT_STEP


async def bottom_sort(s, parent_code: str | None, workspace_code: str) -> int:
    """Позиция под всем рядом: ``min(sort) - SORT_STEP``, а на пустом месте — ``SORT_DEFAULT``.

    Сюда встаёт СВЕЖАЯ задача (``task_create``). Значение считается, а не берётся постоянным:
    ряд, однажды переставленный мышью, перенумерован с шагом ``SORT_STEP`` от своей длины, и
    задача с постоянным ``SORT_DEFAULT`` вклинилась бы в его середину — тем выше, чем короче ряд.

    Вниз, а не наверх: расстановка наверху — работа рук, и свежая строка не должна прыгать через
    неё только потому, что она свежая.
    """
    stmt = (
        select(func.min(TasksLink.sort))
        .join(TasksTask, TasksTask.code == TasksLink.task_code)
        .where(TasksTask.workspace_code == workspace_code)
    )
    if parent_code is None:
        stmt = stmt.where(TasksLink.parent_code.is_(None))
    else:
        stmt = stmt.where(TasksLink.parent_code == parent_code)
    bottom = (await s.execute(stmt)).scalar_one_or_none()
    return SORT_DEFAULT if bottom is None else bottom - SORT_STEP


async def link_get(task_code: str) -> TasksLink | None:
    """Ребро задачи — её место в дереве (родитель, группа, позиция)."""
    async with session_scope() as s:
        return await s.get(TasksLink, task_code)


async def link_list_by_parent(parent_code: str | None) -> list[TasksLink]:
    """Рёбра детей узла по порядку; ``parent_code=None`` — корни (всех пространств)."""
    stmt = select(TasksLink).order_by(TasksLink.sort.desc(), TasksLink.task_code.asc())
    if parent_code is None:
        stmt = stmt.where(TasksLink.parent_code.is_(None))
    else:
        stmt = stmt.where(TasksLink.parent_code == parent_code)
    async with session_scope() as s:
        return list((await s.execute(stmt)).scalars().all())


async def link_map_by_task_codes(task_codes: list[str]) -> dict[str, TasksLink]:
    """``task_code → его ребро`` одним запросом на весь список.

    Место в дереве лежит в отдельной таблице, но читателю (строке списка) оно нужно в той же
    строке, что и поля задачи: без этой карты каждая карточка тянула бы своё ребро отдельным
    запросом — ровно тот N+1, от которого счётчики пространств уже уходят группировкой.
    """
    if not task_codes:
        return {}
    stmt = select(TasksLink).where(TasksLink.task_code.in_(task_codes))
    async with session_scope() as s:
        return {link.task_code: link for link in (await s.execute(stmt)).scalars().all()}


async def link_child_count_by_parent_codes(
    parent_codes: list[str], *, include_deleted: bool = False
) -> dict[str, int]:
    """``parent_code → сколько под ним детей`` одним ``GROUP BY``; узлов без детей в ответе нет.

    Считает живых детей, поэтому таблица связей соединяется с задачами: у ребра отметки
    удаления нет вовсе (она у задачи), и без join в «внутри есть ещё» попала бы ветка, целиком
    лежащая в корзине.
    """
    if not parent_codes:
        return {}
    stmt = (
        select(TasksLink.parent_code, func.count())
        .join(TasksTask, TasksTask.code == TasksLink.task_code)
        .where(TasksLink.parent_code.in_(parent_codes))
        .group_by(TasksLink.parent_code)
    )
    if not include_deleted:
        stmt = stmt.where(TasksTask.deleted_at.is_(None))
    async with session_scope() as s:
        return {code: count for code, count in (await s.execute(stmt)).all()}


async def link_move(
    task_code: str,
    *,
    parent_code: str | None = None,
    sort: int | None = None,
) -> TasksLink | None:
    """Перенести задачу под другого родителя (``None`` — сделать корнем). ``None`` — задачи нет.

    Перенос — это смена места целиком, поэтому по умолчанию ``sort`` встаёт в конец списка новых
    соседей — ``max(sort) + SORT_STEP``.

    Позицию можно назначить явно — тогда перенос и расстановка делаются одним движением, а не
    переносом с последующей правкой: между ними задача успела бы показаться в конце чужого ряда,
    и человек увидел бы промежуточное состояние, которого не просил.
    """
    async with write_scope() as s:
        link = await s.get(TasksLink, task_code)
        if link is None:
            return None
        workspace_code = await _workspace_of(s, task_code)
        if parent_code:
            if parent_code == task_code:
                raise ValueError(
                    f"Task {task_code!r} cannot be its own parent."
                )
            parent_workspace = await _workspace_of(s, parent_code)
            if parent_workspace is None:
                raise ValueError(f"Parent task {parent_code!r} does not exist.")
            if parent_workspace != workspace_code:
                raise ValueError(
                    f"Parent task {parent_code!r} belongs to workspace {parent_workspace!r}, "
                    f"but the task belongs to {workspace_code!r} — a branch never spans "
                    "workspaces."
                )
            if parent_code in await _descendants(s, task_code):
                raise ValueError(
                    f"Task {parent_code!r} is a descendant of {task_code!r} — moving a branch "
                    "under its own child would tear it off the tree into a closed loop."
                )
        # Позиция считается ДО правки строки: запрос в той же сессии сначала сбросил бы в базу
        # незакоммиченное изменение (autoflush), и максимум соседей считался бы уже по
        # наполовину переехавшему дереву.
        place = (
            sort
            if sort is not None
            else await _next_sort(s, parent_code or None, workspace_code, moved_code=task_code)
        )
        link.parent_code = parent_code or None
        link.sort = place
        await s.flush()
        await s.refresh(link)
    return link


async def link_reorder(task_code: str, *, after_code: str | None) -> list[TasksLink] | None:
    """Поставить задачу следом за ``after_code`` среди её соседей и перенумеровать весь ряд.

    ``after_code=None`` — в начало ряда (перетащили выше первой строки). ``None`` в ответе —
    задачи нет; ``ValueError`` — названный сосед из другого ряда, то есть цель перетаскивания
    выбрана неверно.

    **Почему пересчитываются все соседи, а не только переехавшая строка.** Ряд задаёт порядок
    целиком, и держать его на «где-то посередине между соседями» значит рано или поздно упереться
    в место, где середины больше нет: ``sort`` целый, и после десятка перестановок между двумя
    соседними числами вставить нечего. Пересчёт ряда с шагом ``SORT_STEP`` держит промежутки
    ровными всегда, а стоит он одного ``UPDATE`` на строку ряда — рядов длиной в тысячи у одного
    родителя не бывает.

    Соседи — строки с тем же родителем; у корней (``parent_code IS NULL``) родителя нет, поэтому
    ряд ограничен ещё и пространством, иначе в него попали бы корни чужих.

    Порядок ряда до перестановки берётся тот же, в котором его видит список (``sort`` по
    убыванию, дальше по коду): переставляя строку, человек двигает её относительно ТОГО ряда,
    который у него на экране.
    """
    async with write_scope() as s:
        link = await s.get(TasksLink, task_code)
        if link is None:
            return None
        workspace_code = await _workspace_of(s, task_code)

        stmt = (
            select(TasksLink)
            .join(TasksTask, TasksTask.code == TasksLink.task_code)
            .where(TasksTask.workspace_code == workspace_code)
            .order_by(TasksLink.sort.desc(), TasksLink.task_code.asc())
        )
        if link.parent_code is None:
            stmt = stmt.where(TasksLink.parent_code.is_(None))
        else:
            stmt = stmt.where(TasksLink.parent_code == link.parent_code)
        row = list((await s.execute(stmt)).scalars().all())

        if after_code is not None and all(item.task_code != after_code for item in row):
            raise ValueError(
                f"Task {after_code!r} is not a sibling of {task_code!r} — a task can only be "
                "placed among the tasks it shares a parent with."
            )

        order = [item for item in row if item.task_code != task_code]
        at = (
            0
            if after_code is None
            else next(i for i, item in enumerate(order) if item.task_code == after_code) + 1
        )
        order.insert(at, link)

        # Нумеруем сверху вниз: первая строка получает наибольший ``sort``. Нижняя граница —
        # ``SORT_STEP``, чтобы ряд не упирался в ноль и место под будущую строку в самом низу
        # оставалось всегда.
        top = len(order) * SORT_STEP
        for index, item in enumerate(order):
            item.sort = top - index * SORT_STEP
        await s.flush()
        for item in order:
            await s.refresh(item)
    return order


__all__ = [
    "link_child_count_by_parent_codes",
    "link_get",
    "link_list_by_parent",
    "link_map_by_task_codes",
    "link_move",
    "link_reorder",
]
