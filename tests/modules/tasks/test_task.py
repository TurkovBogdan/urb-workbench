"""CRUD задач: рождение вместе с ребром дерева, проверки пространства, статусы и усечение."""

from __future__ import annotations

import pytest

from src.modules.tasks.constants import (
    BODY_MAX,
    CODE_LEN,
    PRIORITY_BURNING,
    SORT_DEFAULT,
    STATUS_DONE,
    STATUS_IN_PROGRESS,
    TASK_PRIORITY_DEFAULT,
    TASK_STATUS_DEFAULT,
    TASK_TYPE_DEFAULT,
    TITLE_MAX,
    TYPE_STANDARD,
)
from src.modules.tasks.crud.group import group_create
from src.modules.tasks.crud.link import link_get
from src.modules.tasks.crud.task import (
    task_create,
    task_get,
    task_list_by_parent,
    task_list_by_workspace,
    task_update,
    task_update_status,
)
from src.modules.workspace.crud.workspace import workspace_create

pytestmark = pytest.mark.db


async def test_create_fills_defaults(db, workspace):
    row = await task_create(workspace_code=workspace.code, title="Починить сборку")

    assert len(row.code) == CODE_LEN
    assert (row.type, row.status, row.priority) == (
        TASK_TYPE_DEFAULT,
        TASK_STATUS_DEFAULT,
        TASK_PRIORITY_DEFAULT,
    )
    assert row.created_by == "human"
    assert row.group_code is None and row.deleted_at is None


async def test_create_writes_the_tree_row_for_a_root_task(db, workspace):
    """Без строки связи задача дереву не принадлежит — значит она создаётся вместе с задачей."""
    row = await task_create(workspace_code=workspace.code, title="Корень")

    link = await link_get(row.code)
    assert link is not None
    assert link.parent_code is None
    assert link.sort == SORT_DEFAULT


async def test_create_with_a_parent_writes_the_edge_to_it(db, workspace):
    parent = await task_create(workspace_code=workspace.code, title="Эпик")

    child = await task_create(
        workspace_code=workspace.code, title="Подзадача", parent_code=parent.code
    )

    assert (await link_get(child.code)).parent_code == parent.code
    assert [row.code for row in await task_list_by_parent(parent.code)] == [child.code]


async def test_root_listing_is_scoped_to_its_workspace(db, workspace):
    other = await workspace_create(title="Личное")
    mine = await task_create(workspace_code=workspace.code, title="Моя")
    await task_create(workspace_code=other.code, title="Чужая")

    roots = await task_list_by_parent(None, workspace_code=workspace.code)

    assert [row.code for row in roots] == [mine.code]


async def test_parent_from_another_workspace_is_refused(db, workspace):
    other = await workspace_create(title="Личное")
    stranger = await task_create(workspace_code=other.code, title="Чужая")

    with pytest.raises(ValueError, match="never spans workspaces"):
        await task_create(
            workspace_code=workspace.code, title="Подзадача", parent_code=stranger.code
        )


async def test_group_from_another_workspace_is_refused(db, workspace):
    other = await workspace_create(title="Личное")
    stranger_group = await group_create(workspace_code=other.code, title="Ремонт")

    with pytest.raises(ValueError, match="never spans workspaces"):
        await task_create(
            workspace_code=workspace.code, title="Задача", group_code=stranger_group.code
        )


async def test_task_in_a_missing_workspace_is_refused(db):
    with pytest.raises(ValueError, match="does not exist"):
        await task_create(workspace_code="0" * CODE_LEN, title="Задача")


async def test_moving_a_task_into_a_foreign_group_is_refused(db, workspace):
    other = await workspace_create(title="Личное")
    stranger_group = await group_create(workspace_code=other.code, title="Ремонт")
    task = await task_create(workspace_code=workspace.code, title="Задача")

    with pytest.raises(ValueError, match="never spans workspaces"):
        await task_update(task.code, group_code=stranger_group.code)


async def test_unknown_dictionary_value_is_refused_by_name(db, workspace):
    """Отказ приходит из CRUD со списком допустимых, а не ``IntegrityError`` из драйвера."""
    with pytest.raises(ValueError, match="Unknown task status"):
        await task_create(workspace_code=workspace.code, title="Задача", status="later")


async def test_update_detaches_the_group_with_an_empty_string(db, workspace):
    group = await group_create(workspace_code=workspace.code, title="Биллинг")
    task = await task_create(
        workspace_code=workspace.code, title="Задача", group_code=group.code
    )

    assert (await task_update(task.code, group_code="")).group_code is None


async def test_status_change_stamps_the_phase_once(db, workspace):
    task = await task_create(workspace_code=workspace.code, title="Задача")

    started = await task_update_status(task.code, STATUS_IN_PROGRESS)
    assert started.started_at is not None and started.completed_at is None

    done = await task_update_status(task.code, STATUS_DONE)
    assert done.completed_at is not None

    reopened = await task_update_status(task.code, STATUS_IN_PROGRESS)
    assert reopened.started_at == started.started_at


async def test_workspace_listing_filters_by_status_and_group(db, workspace):
    group = await group_create(workspace_code=workspace.code, title="Биллинг")
    in_group = await task_create(
        workspace_code=workspace.code, title="В группе", group_code=group.code
    )
    await task_create(workspace_code=workspace.code, title="Без группы")
    await task_update_status(in_group.code, STATUS_DONE)

    by_status = await task_list_by_workspace(workspace.code, status=STATUS_DONE)
    unfiled = await task_list_by_workspace(workspace.code, group_code="")

    assert [row.code for row in by_status] == [in_group.code]
    assert [row.title for row in unfiled] == ["Без группы"]


async def test_workspace_listing_follows_the_manual_order_not_priority(db, workspace):
    """Порядок списка задаёт расстановка (`sort`), а не важность.

    Важность из порядка ушла намеренно: список переставляют мышью, и строка, поднятая наверх,
    возвращалась бы вниз следующим же запросом, если бы сортировал приоритет. Свежая задача
    встаёт ПОД рядом (`bottom_sort`), поэтому горящая, заведённая второй, стоит второй — важность
    на её место больше не влияет.
    """
    await task_create(workspace_code=workspace.code, title="Обычная")
    await task_create(
        workspace_code=workspace.code, title="Горит", priority=PRIORITY_BURNING
    )

    titles = [row.title for row in await task_list_by_workspace(workspace.code)]

    assert titles == ["Обычная", "Горит"]


async def test_long_title_is_clipped_by_code_points(db, workspace):
    row = await task_create(
        workspace_code=workspace.code,
        title="я" * (TITLE_MAX + 50),
        type=TYPE_STANDARD,
    )

    assert len(row.title) == TITLE_MAX and row.title[-1] == "я"
    assert (await task_get(row.code)).type == TYPE_STANDARD


async def test_the_whole_brief_is_kept_apart(db, workspace):
    """Постановка живёт в четырёх разных полях, и слой их не сливает в одно."""
    row = await task_create(
        workspace_code=workspace.code,
        title="Перевести модуль на группы",
        description="Зона называется группой во всех слоях",
        context="Смотреть src/modules/tasks",
        constraints="Не трогать модуль workspace",
        criteria="Тесты зелёные, схема без дрейфа",
        body="План: сначала модели, потом миграции",
        type=TYPE_STANDARD,
    )

    assert row.description == "Зона называется группой во всех слоях"
    assert row.context == "Смотреть src/modules/tasks"
    assert row.constraints == "Не трогать модуль workspace"
    assert row.criteria == "Тесты зелёные, схема без дрейфа"
    assert row.body.startswith("План:")


async def test_overlong_plan_is_refused_not_clipped(db, workspace):
    """План отказывает, в отличие от заголовка: молча срезался бы хвост с последними шагами."""
    with pytest.raises(ValueError, match="shorten it by"):
        await task_create(
            workspace_code=workspace.code,
            title="Слишком длинный план",
            body="x" * (BODY_MAX + 1),
        )
