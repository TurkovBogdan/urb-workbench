"""Дерево задач: перенос ветки, позиция среди соседей, группа и защита от петли."""

from __future__ import annotations

import pytest

from src.modules.tasks.constants import SORT_DEFAULT, SORT_STEP
from src.modules.tasks.crud.link import (
    link_get,
    link_list_by_parent,
    link_move,
    link_reorder,
)
from src.modules.tasks.crud.task import task_create
from src.modules.workspace.crud.workspace import workspace_create

pytestmark = pytest.mark.db


async def test_move_puts_the_branch_at_the_end_of_the_new_list(db, workspace):
    """Перенос — смена места целиком: ветка встаёт под всем рядом новых соседей."""
    old_parent = await task_create(workspace_code=workspace.code, title="Старый эпик")
    new_parent = await task_create(workspace_code=workspace.code, title="Новый эпик")
    neighbour = await task_create(
        workspace_code=workspace.code, title="Сосед", parent_code=new_parent.code
    )
    moved = await task_create(
        workspace_code=workspace.code, title="Переезжает", parent_code=old_parent.code
    )

    link = await link_move(moved.code, parent_code=new_parent.code)

    assert link.parent_code == new_parent.code
    assert link.sort == (await link_get(neighbour.code)).sort + SORT_STEP


async def test_move_onto_an_empty_place_starts_from_the_default_position(db, workspace):
    parent = await task_create(workspace_code=workspace.code, title="Эпик")
    task = await task_create(workspace_code=workspace.code, title="Задача")
    await link_move(task.code, parent_code=parent.code)

    assert (await link_get(task.code)).sort == SORT_DEFAULT


async def test_move_without_a_parent_makes_the_task_a_root(db, workspace):
    parent = await task_create(workspace_code=workspace.code, title="Эпик")
    child = await task_create(
        workspace_code=workspace.code, title="Ребёнок", parent_code=parent.code
    )

    link = await link_move(child.code, parent_code=None)

    assert link.parent_code is None
    assert child.code in {row.task_code for row in await link_list_by_parent(None)}


async def test_root_position_is_counted_within_its_own_workspace(db, workspace):
    """Корни чужого пространства — не соседи: иначе позиция зависела бы от посторонних строк."""
    other = await workspace_create(title="Личное")
    stranger = await task_create(workspace_code=other.code, title="Чужой корень")
    await link_move(stranger.code, parent_code=None)
    task = await task_create(workspace_code=workspace.code, title="Задача")

    assert (await link_move(task.code, parent_code=None)).sort == SORT_DEFAULT


async def test_move_under_a_foreign_workspace_is_refused(db, workspace):
    other = await workspace_create(title="Личное")
    stranger = await task_create(workspace_code=other.code, title="Чужая")
    task = await task_create(workspace_code=workspace.code, title="Задача")

    with pytest.raises(ValueError, match="never spans workspaces"):
        await link_move(task.code, parent_code=stranger.code)


async def test_move_under_its_own_descendant_is_refused(db, workspace):
    root = await task_create(workspace_code=workspace.code, title="Эпик")
    child = await task_create(
        workspace_code=workspace.code, title="Ребёнок", parent_code=root.code
    )

    with pytest.raises(ValueError, match="descendant"):
        await link_move(root.code, parent_code=child.code)

    with pytest.raises(ValueError, match="own parent"):
        await link_move(root.code, parent_code=root.code)


async def test_children_are_listed_from_the_bigger_sort_down(db, workspace):
    parent = await task_create(workspace_code=workspace.code, title="Эпик")
    first = await task_create(
        workspace_code=workspace.code, title="Первая", parent_code=parent.code
    )
    second = await task_create(
        workspace_code=workspace.code, title="Вторая", parent_code=parent.code
    )
    await link_move(second.code, parent_code=parent.code)  # поднимает её над соседом

    codes = [row.task_code for row in await link_list_by_parent(parent.code)]

    assert codes == [second.code, first.code]


async def test_move_of_a_missing_task_reports_none(db, workspace):
    assert await link_move("0" * 10, parent_code=None) is None


# ── Перестановка перетаскиванием ──────────────────────────────────────────────


async def _row(workspace_code: str, *titles: str) -> list[str]:
    """Ряд корней в порядке заведения; возвращает коды в том же порядке."""
    codes = []
    for title in titles:
        task = await task_create(workspace_code=workspace_code, title=title)
        codes.append(task.code)
    return codes


async def test_reorder_places_the_task_after_the_named_neighbour(db, workspace):
    first, second, third = await _row(workspace.code, "Первая", "Вторая", "Третья")

    await link_reorder(third, after_code=first)

    codes = [row.task_code for row in await link_list_by_parent(None)]
    assert codes == [first, third, second]


async def test_reorder_without_a_neighbour_puts_the_task_on_top(db, workspace):
    first, second, third = await _row(workspace.code, "Первая", "Вторая", "Третья")

    await link_reorder(third, after_code=None)

    codes = [row.task_code for row in await link_list_by_parent(None)]
    assert codes == [third, first, second]


async def test_reorder_renumbers_the_whole_row_with_an_even_step(db, workspace):
    """Пересчёт ряда — то, ради чего перестановка вообще трогает соседей.

    Промежутки после неё одинаковые: иначе после десятка перестановок между соседними числами
    не осталось бы места, и следующая вставка не смогла бы найти себе значение.
    """
    first, second, third = await _row(workspace.code, "Первая", "Вторая", "Третья")

    await link_reorder(second, after_code=None)

    sorts = [row.sort for row in await link_list_by_parent(None)]
    assert sorts == [3 * SORT_STEP, 2 * SORT_STEP, SORT_STEP]


async def test_reorder_keeps_a_branch_out_of_the_root_row(db, workspace):
    """Соседи — только строки того же родителя: ряд корней ветку под ними не видит."""
    parent, other_root = await _row(workspace.code, "Эпик", "Другой корень")
    child = await task_create(
        workspace_code=workspace.code, title="Подзадача", parent_code=parent
    )

    with pytest.raises(ValueError):
        await link_reorder(child.code, after_code=other_root)


async def test_reorder_of_a_missing_task_reports_none(db, workspace):
    assert await link_reorder("0" * 10, after_code=None) is None


async def test_a_fresh_task_lands_under_the_arranged_row(db, workspace):
    """Свежая задача встаёт ПОД рядом, а не в его середину: наверху — расстановка рук."""
    first, second = await _row(workspace.code, "Первая", "Вторая")
    await link_reorder(second, after_code=None)

    third = await task_create(workspace_code=workspace.code, title="Третья")

    codes = [row.task_code for row in await link_list_by_parent(None)]
    assert codes == [second, first, third.code]
