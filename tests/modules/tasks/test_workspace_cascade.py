"""Что происходит с группами и задачами, когда пространство удаляют, — и чем их считают.

Оба вопроса живут здесь, а не в тестах ``workspace``: модуль уровня 1 про наши таблицы не знает
и знать не должен, а каскад и счётчики — это поведение НАШЕЙ стороны границы. Там проверяется
механизм (счётчик объявили — он приехал в карточку), здесь — что именно мы в этот механизм кладём.

Пространство заводится через CRUD соседнего модуля: своей ручки у нас нет, и обходить его прямой
вставкой значило бы проверять не тот путь, которым ходит приложение.
"""

from __future__ import annotations

import pytest

from src.modules.tasks.crud import group as group_crud
from src.modules.tasks.crud import task as task_crud
from src.modules.workspace.crud import workspace as workspace_crud

pytestmark = pytest.mark.db


async def _filled(db, title: str = "Работа"):
    """Пространство с одной группой и одной задачей — минимум, на котором видно и каскад, и счёт."""
    workspace = await workspace_crud.workspace_create(title=title)
    group = await group_crud.group_create(workspace_code=workspace.code, title="Биллинг")
    task = await task_crud.task_create(
        workspace_code=workspace.code, group_code=group.code, title="Счёт"
    )
    return workspace, group, task


# ── каскад ────────────────────────────────────────────────────────────────────


async def test_soft_delete_of_a_workspace_keeps_our_rows(db):
    """Мягкое удаление обратимо без следа: зона и задача остаются на месте со своими ссылками."""
    workspace, group, task = await _filled(db)

    await workspace_crud.workspace_delete(workspace.code)

    assert (await group_crud.group_get(group.code)) is not None
    assert (await task_crud.task_get(task.code)) is not None


async def test_purge_of_a_workspace_takes_our_rows_with_it(db):
    """Физическое удаление уносит содержимое каскадом FK — возвращать после него нечего."""
    workspace, group, task = await _filled(db)

    await workspace_crud.workspace_delete(workspace.code, hard=True)

    assert (await group_crud.group_get(group.code, include_deleted=True)) is None
    assert (await task_crud.task_get(task.code, include_deleted=True)) is None


async def test_purge_leaves_the_neighbour_workspace_untouched(db):
    """Каскад идёт по FK, а не по таблице целиком: соседнее пространство не при чём."""
    doomed, _, _ = await _filled(db, "Под снос")
    _, kept_group, kept_task = await _filled(db, "Остаётся")

    await workspace_crud.workspace_delete(doomed.code, hard=True)

    assert (await group_crud.group_get(kept_group.code)) is not None
    assert (await task_crud.task_get(kept_task.code)) is not None


# ── счётчики, которые модуль отдаёт пространству ──────────────────────────────


async def test_counters_see_only_live_rows(db):
    """Счётчик обещает то, что человек внутри найдёт: удалённая зона в него не входит."""
    workspace, _, _ = await _filled(db)
    second = await group_crud.group_create(workspace_code=workspace.code, title="Вторая")
    await group_crud.group_delete(second.code)

    groups = await group_crud.group_count_by_workspace_codes([workspace.code])
    tasks = await task_crud.task_count_by_workspace_codes([workspace.code])

    assert (groups[workspace.code], tasks[workspace.code]) == (1, 1)


async def test_counters_do_not_leak_across_workspaces(db):
    """Считаем по коду пространства: соседнее в число не подмешивается."""
    mine, _, _ = await _filled(db)
    await _filled(db, "Личное")

    groups = await group_crud.group_count_by_workspace_codes([mine.code])

    assert groups[mine.code] == 1


async def test_counters_skip_a_workspace_without_rows(db):
    """Пустого пространства в ответе нет вовсе — ноль подставляет сборка на стороне карточки."""
    empty = await workspace_crud.workspace_create(title="Пустое")

    groups = await group_crud.group_count_by_workspace_codes([empty.code])

    assert groups == {}
