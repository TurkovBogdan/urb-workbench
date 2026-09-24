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
from src.modules.tasks.crud.group import group_create
from src.modules.tasks.crud.task import task_create, task_regroup, task_update
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


async def test_move_under_its_own_child_is_refused_as_a_second_level(db, workspace):
    """Петлю отсекает правило одного уровня: ребёнок — подзадача, под неё не кладут никого."""
    root = await task_create(workspace_code=workspace.code, title="Эпик")
    child = await task_create(
        workspace_code=workspace.code, title="Ребёнок", parent_code=root.code
    )

    with pytest.raises(ValueError, match="itself a subtask"):
        await link_move(root.code, parent_code=child.code)
    assert (await link_get(root.code)).parent_code is None

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


# ── ряд корня — его группа ────────────────────────────────────────────────────
# Экран раскладывает корни карточками по группам, и строку переставляют ВНУТРИ карточки. Пока ряд
# был общим на пространство, бросок на верх карточки означал «в начало всего пространства»:
# внутри группы выглядело верно, а в базе задача перепрыгивала через соседние группы.


async def test_root_rows_of_two_groups_do_not_touch_each_other(db, workspace):
    first = await group_create(workspace_code=workspace.code, title="Биллинг")
    second = await group_create(workspace_code=workspace.code, title="Интерфейс")
    alone = await task_create(
        workspace_code=workspace.code, title="Одна в своей группе", group_code=second.code
    )
    top = await task_create(
        workspace_code=workspace.code, title="Первая", group_code=first.code
    )
    bottom = await task_create(
        workspace_code=workspace.code, title="Вторая", group_code=first.code
    )

    # Перестановка в чужой группе не должна ни сдвинуть, ни перенумеровать соседку.
    before = (await link_get(alone.code)).sort
    await link_reorder(bottom.code, after_code=None)

    assert (await link_get(alone.code)).sort == before
    assert (await link_get(bottom.code)).sort > (await link_get(top.code)).sort


async def test_a_fresh_task_starts_its_own_row_in_an_empty_group(db, workspace):
    """Ряд пустой группы начинается с умолчания, а не продолжает чужой."""
    filled = await group_create(workspace_code=workspace.code, title="Биллинг")
    empty = await group_create(workspace_code=workspace.code, title="Интерфейс")
    await task_create(workspace_code=workspace.code, title="Занятая", group_code=filled.code)

    fresh = await task_create(
        workspace_code=workspace.code, title="Первая в группе", group_code=empty.code
    )

    assert (await link_get(fresh.code)).sort == SORT_DEFAULT


async def test_unfiled_roots_are_a_row_of_their_own(db, workspace):
    """«Без группы» — такой же ряд, а не отсутствие ряда."""
    group = await group_create(workspace_code=workspace.code, title="Биллинг")
    filed = await task_create(
        workspace_code=workspace.code, title="Разложенная", group_code=group.code
    )
    first = await task_create(workspace_code=workspace.code, title="Первая без группы")
    second = await task_create(workspace_code=workspace.code, title="Вторая без группы")

    before = (await link_get(filed.code)).sort
    await link_reorder(second.code, after_code=None)

    assert (await link_get(filed.code)).sort == before
    assert (await link_get(second.code)).sort > (await link_get(first.code)).sort


async def test_reorder_against_a_task_of_another_group_is_refused(db, workspace):
    """Сосед из чужой карточки — неверно выбранная цель, а не новая позиция."""
    first = await group_create(workspace_code=workspace.code, title="Биллинг")
    second = await group_create(workspace_code=workspace.code, title="Интерфейс")
    mine = await task_create(
        workspace_code=workspace.code, title="Своя", group_code=first.code
    )
    alien = await task_create(
        workspace_code=workspace.code, title="Чужая", group_code=second.code
    )

    with pytest.raises(ValueError):
        await link_reorder(mine.code, after_code=alien.code)


async def test_a_subtask_keeps_its_row_by_parent_not_by_group(db, workspace):
    """У подзадачи ряд задан родителем: корни той же группы ей не соседи."""
    group = await group_create(workspace_code=workspace.code, title="Биллинг")
    parent = await task_create(
        workspace_code=workspace.code, title="Эпик", group_code=group.code
    )
    root_neighbour = await task_create(
        workspace_code=workspace.code, title="Корень той же группы", group_code=group.code
    )
    first = await task_create(
        workspace_code=workspace.code, title="Первая", parent_code=parent.code
    )
    second = await task_create(
        workspace_code=workspace.code, title="Вторая", parent_code=parent.code
    )
    before = (await link_get(root_neighbour.code)).sort

    await link_reorder(second.code, after_code=None)

    assert (await link_get(second.code)).sort > (await link_get(first.code)).sort
    assert (await link_get(root_neighbour.code)).sort == before


async def test_changing_the_group_puts_the_task_at_the_end_of_the_new_row(db, workspace):
    """Переезд между группами — это переезд между рядами: прежнее число к новому не относится."""
    source = await group_create(workspace_code=workspace.code, title="Биллинг")
    target = await group_create(workspace_code=workspace.code, title="Интерфейс")
    settled = await task_create(
        workspace_code=workspace.code, title="Обжитая", group_code=target.code
    )
    # Ряд принимающей группы уже переставляли руками, поэтому он перенумерован от своей длины и
    # стоит НИЖЕ умолчания. Переезжающая приходит со свежим числом — без переклейки она встала бы
    # в новом ряду выше обжитой только потому, что в старом её никто не двигал.
    await link_reorder(settled.code, after_code=None)
    moved = await task_create(
        workspace_code=workspace.code, title="Переезжает", group_code=source.code
    )
    assert (await link_get(moved.code)).sort > (await link_get(settled.code)).sort

    await task_update(moved.code, group_code=target.code)

    assert (await link_get(moved.code)).sort < (await link_get(settled.code)).sort


async def test_regroup_puts_the_batch_at_the_end_of_the_new_row(db, workspace):
    source = await group_create(workspace_code=workspace.code, title="Биллинг")
    target = await group_create(workspace_code=workspace.code, title="Интерфейс")
    settled = await task_create(
        workspace_code=workspace.code, title="Обжитая", group_code=target.code
    )
    await link_reorder(settled.code, after_code=None)
    moved = await task_create(
        workspace_code=workspace.code, title="Переезжает", group_code=source.code
    )

    await task_regroup([moved.code], target.code)

    assert (await link_get(moved.code)).sort < (await link_get(settled.code)).sort
