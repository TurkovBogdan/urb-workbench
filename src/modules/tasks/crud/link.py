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
from src.modules.tasks.constants import SORT_DEFAULT, SORT_STEP, TASK_STATUSES_TERMINAL
from src.modules.tasks.models.group import TasksGroup
from src.modules.tasks.models.link import TasksLink
from src.modules.tasks.models.task import TasksTask


async def _workspace_of(s, task_code: str) -> str | None:
    """Пространство задачи (``None`` — задачи нет)."""
    stmt = select(TasksTask.workspace_code).where(TasksTask.code == task_code)
    return (await s.execute(stmt)).scalar_one_or_none()


async def _group_of(s, task_code: str) -> str | None:
    """Группа задачи; ``None`` — задача не разложена (или её нет — зовут после проверки)."""
    stmt = select(TasksTask.group_code).where(TasksTask.code == task_code)
    return (await s.execute(stmt)).scalar_one_or_none()


def _siblings(stmt, parent_code: str | None, workspace_code: str, group_code: str | None):
    """Сузить запрос до РЯДА СОСЕДЕЙ — единственное место, где это правило записано.

    У подзадачи соседи — дети того же родителя, и группа тут ни при чём: место в дереве задаёт
    родитель, а собственная группа подзадачи на него не влияет (в секциях списка показываются
    только корни).

    У КОРНЯ родителя нет, и рядом ему служит группа: на экране задачи разложены карточками по
    группам, человек переставляет строку внутри своей карточки — и ряд обязан совпадать с тем,
    что он двигает. Пока ряд был общим на пространство, бросок на верх карточки означал «в начало
    всего пространства»: внутри группы выглядело верно, а в базе задача перепрыгивала через
    соседние группы. «Без группы» — такой же ряд (``group_code IS NULL``), а не отсутствие ряда.

    Пространство в условии остаётся и при группе: у неразложенных задач общего кода группы нет, и
    без него в ряд попали бы чужие.
    """
    stmt = stmt.where(TasksTask.workspace_code == workspace_code)
    if parent_code is not None:
        return stmt.where(TasksLink.parent_code == parent_code)
    stmt = stmt.where(TasksLink.parent_code.is_(None))
    if group_code is None:
        return stmt.where(TasksTask.group_code.is_(None))
    return stmt.where(TasksTask.group_code == group_code)


async def _next_sort(
    s,
    parent_code: str | None,
    workspace_code: str,
    group_code: str | None,
    *,
    moved_code: str,
) -> int:
    """Позиция в конце ряда соседей: ``max(sort) + SORT_STEP``, а на пустом месте — ``SORT_DEFAULT``.

    Сама переезжающая задача из ряда исключена — иначе перестановка внутри того же списка всё
    время двигала бы её относительно собственной прежней позиции.
    """
    stmt = _siblings(
        select(func.max(TasksLink.sort))
        .join(TasksTask, TasksTask.code == TasksLink.task_code)
        .where(TasksLink.task_code != moved_code),
        parent_code,
        workspace_code,
        group_code,
    )
    top = (await s.execute(stmt)).scalar_one_or_none()
    return SORT_DEFAULT if top is None else top + SORT_STEP


async def bottom_sort(
    s,
    parent_code: str | None,
    workspace_code: str,
    group_code: str | None = None,
    *,
    moved_code: str | None = None,
) -> int:
    """Позиция под всем рядом: ``min(sort) - SORT_STEP``, а на пустом месте — ``SORT_DEFAULT``.

    Сюда встаёт СВЕЖАЯ задача (``task_create``) и та, что сменила группу: в новом ряду у неё нет
    заслуженного места, и приписывать ей чужое по старому числу — значит ставить её в середину
    наугад. Значение считается, а не берётся постоянным: ряд, однажды переставленный мышью,
    перенумерован с шагом ``SORT_STEP`` от своей длины, и задача с постоянным ``SORT_DEFAULT``
    вклинилась бы в его середину — тем выше, чем короче ряд.

    Вниз, а не наверх: расстановка наверху — работа рук, и свежая строка не должна прыгать через
    неё только потому, что она свежая.

    ``moved_code`` исключает из ряда саму переезжающую задачу — её прежнее число к новому ряду
    отношения не имеет, а попав в ``min``, оно утянуло бы расчёт за собой.
    """
    stmt = _siblings(
        select(func.min(TasksLink.sort)).join(
            TasksTask, TasksTask.code == TasksLink.task_code
        ),
        parent_code,
        workspace_code,
        group_code,
    )
    if moved_code is not None:
        stmt = stmt.where(TasksLink.task_code != moved_code)
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


async def require_root_parent(s, parent_code: str) -> None:
    """Отказ, если названный родитель сам подзадача: дерево здесь в один уровень.

    Второй уровень не запрещён схемой — ребро ссылается на любую задачу, — поэтому держит его
    только этот слой, на каждом пути, который ставит родителя: заведение и перенос.
    """
    parent_link = await s.get(TasksLink, parent_code)
    if parent_link is not None and parent_link.parent_code is not None:
        raise ValueError(
            f"Task {parent_code!r} is itself a subtask of {parent_link.parent_code!r}, and the "
            "tree is one level deep — a subtask has no subtasks of its own. Put the task under "
            f"{parent_link.parent_code!r} instead, next to {parent_code!r}."
        )


async def require_parent_group_alive(s, parent_code: str, group_code: str | None) -> None:
    """Отказ, если группа родителя удалена: подзадача получила бы её и пропала из списка.

    Экран раскладывает задачи по живым группам, и подзадача с кодом удалённой группы не видна
    нигде, хотя живёт и считается.
    """
    if group_code is None:
        return
    group = await s.get(TasksGroup, group_code)
    if group is None or group.deleted_at is not None:
        raise ValueError(
            f"Parent task {parent_code!r} is filed under group {group_code!r}, which does not "
            "exist (or is deleted) — a subtask takes its parent's group and would vanish from "
            f"the list. Refile {parent_code!r} into a live group first."
        )


def require_open_parent(parent_code: str, parent_status: str, child_status: str) -> None:
    """Отказ, если под закрытую задачу кладут незакрытую.

    Принятая или отменённая работа новых частей не получает: открытая подзадача под ней — это
    работа, которую никто не увидит в очереди. Закрытую же можно: разложить по эпику то, что уже
    сделано, — это приборка истории, а не новая работа.
    """
    if parent_status in TASK_STATUSES_TERMINAL and child_status not in TASK_STATUSES_TERMINAL:
        raise ValueError(
            f"Parent task {parent_code!r} is {parent_status!r} — accepted or called-off work "
            f"takes no new open parts, and this one is {child_status!r}. Pick a live parent, or "
            "ask the person to reopen that one. Only a closed task may go under a closed one."
        )


async def _require_parent_for(s, task: TasksTask, parent_code: str) -> TasksTask:
    """Родитель, под которого задачу можно положить, или отказ, называющий причину."""
    if parent_code == task.code:
        raise ValueError(f"Task {task.code!r} cannot be its own parent.")
    parent = await s.get(TasksTask, parent_code)
    if parent is None or parent.deleted_at is not None:
        raise ValueError(f"Parent task {parent_code!r} does not exist (or is deleted).")
    if parent.workspace_code != task.workspace_code:
        raise ValueError(
            f"Parent task {parent_code!r} belongs to workspace {parent.workspace_code!r}, but "
            f"the task belongs to {task.workspace_code!r} — a branch never spans workspaces."
        )
    require_open_parent(parent_code, parent.status, task.status)
    await require_parent_group_alive(s, parent_code, parent.group_code)
    await require_root_parent(s, parent_code)
    # Подзадачи из корзины тоже считаются: восстановление вернёт их на прежнее место в дереве, и
    # под перенесённой задачей они стали бы вторым уровнем, которого никто не собирал.
    children_query = (
        select(TasksLink.task_code, TasksTask.deleted_at.is_not(None))
        .join(TasksTask, TasksTask.code == TasksLink.task_code)
        .where(TasksLink.parent_code == task.code)
    )
    children = (await s.execute(children_query)).all()
    if children:
        named = ", ".join(
            f"{code!r} (in the bin)" if binned else repr(code) for code, binned in children
        )
        bin_hint = (
            " A subtask in the bin has to be restored or purged first — that is the person's."
            if any(binned for _, binned in children)
            else ""
        )
        raise ValueError(
            f"Task {task.code!r} has subtasks of its own ({named}), and the tree is one level "
            "deep — it cannot become a subtask. Move its subtasks out first (to the root or "
            f"under another task), then move this one.{bin_hint}"
        )
    return parent


async def link_move_in(
    s, task: TasksTask, parent_code: str | None, *, sort: int | None = None
) -> TasksLink:
    """Перенести задачу внутри чужой транзакции: ``parent_code`` — под него, ``""``/``None`` — в
    корень. ``sort=None`` — под всем новым рядом, как встаёт переложенная в другую группу.

    Своей сессии нет намеренно: ``task_update`` переносит задачу и правит её карточку одним
    вызовом, и отказ переноса обязан откатить правку вместе с ним — иначе агент прочтёт ошибку
    как «ничего не произошло», хотя заголовок уже переписан.

    Подзадача получает группу родителя: группа говорит, о чём работа, а часть работы — о том
    же, о чём целое. Вынесенная в корень свою группу сохраняет — это группа бывшего родителя.
    """
    link = await s.get(TasksLink, task.code)
    parent = await _require_parent_for(s, task, parent_code) if parent_code else None
    group_code = parent.group_code if parent else task.group_code
    place = (
        sort
        if sort is not None
        else await bottom_sort(
            s, parent_code or None, task.workspace_code, group_code, moved_code=task.code
        )
    )
    link.parent_code = parent_code or None
    link.sort = place
    task.group_code = group_code
    return link


async def link_move(
    task_code: str,
    *,
    parent_code: str | None = None,
    sort: int | None = None,
) -> TasksLink | None:
    """Перенести задачу под другого родителя (``None`` — сделать корнем). ``None`` — задачи нет.

    Правила переноса — в ``link_move_in``. Здесь только позиция по умолчанию: наверх нового
    ряда, ``max(sort) + SORT_STEP``.

    Позицию можно назначить явно — тогда перенос и расстановка делаются одним движением, а не
    переносом с последующей правкой: между ними задача успела бы показаться в конце чужого ряда,
    и человек увидел бы промежуточное состояние, которого не просил.
    """
    async with write_scope() as s:
        task = await s.get(TasksTask, task_code)
        if task is None or await s.get(TasksLink, task_code) is None:
            return None
        place = (
            sort
            if sort is not None
            else await _next_sort(
                s,
                parent_code or None,
                task.workspace_code,
                task.group_code,
                moved_code=task_code,
            )
        )
        link = await link_move_in(s, task, parent_code, sort=place)
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

    Кто соседи — ``_siblings``: у подзадачи это дети её родителя, у корня — задачи его группы.

    Порядок ряда до перестановки берётся тот же, в котором его видит список (``sort`` по
    убыванию, дальше по коду): переставляя строку, человек двигает её относительно ТОГО ряда,
    который у него на экране.
    """
    async with write_scope() as s:
        order = await link_reorder_in(s, task_code, after_code=after_code)
        if order is None:
            return None
        await s.flush()
        for item in order:
            await s.refresh(item)
    return order


async def link_reorder_in(
    s, task_code: str, *, after_code: str | None
) -> list[TasksLink] | None:
    """``link_reorder`` внутри чужой транзакции — для перетаскивания, которое заодно переносит.

    Ряд читается из той же сессии и обязан видеть уже сделанный в ней перенос: соседи — это ряд,
    куда строку бросили, а не тот, откуда её взяли. Сессии фабрики не сбрасывают правки сами
    (``autoflush=False``), поэтому перенос сбрасывается в базу явно, до чтения ряда.
    """
    await s.flush()
    link = await s.get(TasksLink, task_code)
    if link is None:
        return None
    workspace_code = await _workspace_of(s, task_code)

    stmt = _siblings(
        select(TasksLink)
        .join(TasksTask, TasksTask.code == TasksLink.task_code)
        .order_by(TasksLink.sort.desc(), TasksLink.task_code.asc()),
        link.parent_code,
        workspace_code,
        await _group_of(s, task_code),
    )
    row = list((await s.execute(stmt)).scalars().all())

    if after_code is not None and all(item.task_code != after_code for item in row):
        raise ValueError(
            f"Task {after_code!r} is not a sibling of {task_code!r} — a task can only be "
            "placed among the tasks it shares a parent with (a top-level task — among the "
            "tasks of its group)."
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
    return order


__all__ = [
    "link_child_count_by_parent_codes",
    "link_get",
    "link_list_by_parent",
    "link_map_by_task_codes",
    "link_move",
    "link_move_in",
    "link_reorder",
    "link_reorder_in",
    "require_open_parent",
    "require_parent_group_alive",
    "require_root_parent",
]
