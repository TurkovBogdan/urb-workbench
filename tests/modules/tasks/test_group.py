"""CRUD групп: принадлежность пространству, порядок в списке и логическое удаление."""

from __future__ import annotations

import pytest

from src.modules.tasks.constants import CODE_LEN, SORT_DEFAULT
from src.modules.tasks.crud.group import (
    group_create,
    group_delete,
    group_find_by_title,
    group_get,
    group_list_by_workspace,
    group_reorder,
    group_restore,
    group_update,
)
from src.modules.workspace.crud.workspace import workspace_create, workspace_delete

pytestmark = pytest.mark.db


async def test_create_binds_the_group_to_the_workspace(db, workspace):
    row = await group_create(workspace_code=workspace.code, title="Биллинг")

    assert row.workspace_code == workspace.code
    assert row.sort == SORT_DEFAULT


async def test_create_in_a_missing_workspace_is_refused(db):
    with pytest.raises(ValueError, match="does not exist"):
        await group_create(workspace_code="0" * CODE_LEN, title="Биллинг")


async def test_create_in_a_deleted_workspace_is_refused(db, workspace):
    """Удалённое пространство для всего остального кода не существует — группе там не место."""
    await workspace_delete(workspace.code)

    with pytest.raises(ValueError, match="does not exist"):
        await group_create(workspace_code=workspace.code, title="Биллинг")


async def test_list_puts_the_bigger_sort_first(db, workspace):
    await group_create(workspace_code=workspace.code, title="Интерфейс", sort=100)
    await group_create(workspace_code=workspace.code, title="Биллинг", sort=900)

    titles = [row.title for row in await group_list_by_workspace(workspace.code)]

    assert titles == ["Биллинг", "Интерфейс"]


async def test_list_is_scoped_to_its_workspace(db, workspace):
    other = await workspace_create(title="Личное")
    await group_create(workspace_code=workspace.code, title="Биллинг")
    await group_create(workspace_code=other.code, title="Ремонт")

    assert [row.title for row in await group_list_by_workspace(other.code)] == ["Ремонт"]


async def test_create_without_sort_lands_at_the_end(db, workspace):
    """Умолчание — «ниже всех», а не ``SORT_DEFAULT``: иначе место новой решал бы тайбрейк."""
    await group_create(workspace_code=workspace.code, title="Биллинг")
    await group_create(workspace_code=workspace.code, title="Аудит")

    titles = [row.title for row in await group_list_by_workspace(workspace.code)]

    assert titles == ["Биллинг", "Аудит"]


async def test_find_by_title_ignores_case(db, workspace):
    row = await group_create(workspace_code=workspace.code, title="Биллинг")

    assert (await group_find_by_title(workspace.code, "  биллинг ")).code == row.code


async def test_find_by_title_skips_the_deleted_and_the_neighbours(db, workspace):
    """Занятым название считается только живой группой своего пространства."""
    other = await workspace_create(title="Личное")
    await group_create(workspace_code=other.code, title="Биллинг")
    gone = await group_create(workspace_code=workspace.code, title="Биллинг")
    await group_delete(gone.code)

    assert await group_find_by_title(workspace.code, "Биллинг") is None


async def test_reorder_puts_the_group_under_its_anchor(db, workspace):
    top = await group_create(workspace_code=workspace.code, title="Биллинг")
    await group_create(workspace_code=workspace.code, title="Интерфейс")
    last = await group_create(workspace_code=workspace.code, title="Инфра")

    await group_reorder(last.code, after=top.code)

    titles = [row.title for row in await group_list_by_workspace(workspace.code)]
    assert titles == ["Биллинг", "Инфра", "Интерфейс"]


async def test_reorder_puts_the_group_above_its_anchor(db, workspace):
    top = await group_create(workspace_code=workspace.code, title="Биллинг")
    last = await group_create(workspace_code=workspace.code, title="Инфра")

    await group_reorder(last.code, before=top.code)

    titles = [row.title for row in await group_list_by_workspace(workspace.code)]
    assert titles == ["Инфра", "Биллинг"]


async def test_reorder_leaves_the_list_evenly_spaced(db, workspace):
    """Перенумерация — весь список сверху вниз: на кончившемся зазоре порядок не ломается."""
    first = await group_create(workspace_code=workspace.code, title="Биллинг", sort=500)
    second = await group_create(workspace_code=workspace.code, title="Интерфейс", sort=500)
    third = await group_create(workspace_code=workspace.code, title="Инфра", sort=500)

    await group_reorder(third.code, before=first.code)

    rows = await group_list_by_workspace(workspace.code)
    assert [row.code for row in rows] == [third.code, first.code, second.code]
    assert len({row.sort for row in rows}) == 3


async def test_reorder_refuses_a_foreign_anchor(db, workspace):
    other = await workspace_create(title="Личное")
    mine = await group_create(workspace_code=workspace.code, title="Биллинг")
    stranger = await group_create(workspace_code=other.code, title="Ремонт")

    with pytest.raises(ValueError, match="never spans workspaces"):
        await group_reorder(mine.code, after=stranger.code)


async def test_reorder_refuses_itself_as_the_anchor(db, workspace):
    row = await group_create(workspace_code=workspace.code, title="Биллинг")

    with pytest.raises(ValueError, match="relative to itself"):
        await group_reorder(row.code, after=row.code)


async def test_reorder_needs_exactly_one_point_of_reference(db, workspace):
    row = await group_create(workspace_code=workspace.code, title="Биллинг")

    with pytest.raises(ValueError, match="exactly one"):
        await group_reorder(row.code)
    with pytest.raises(ValueError, match="exactly one"):
        await group_reorder(row.code, after=row.code, before=row.code)


async def test_update_sort_zero_is_applied(db, workspace):
    """``0`` — валидная позиция: условие смотрит на ``is not None``, а не на истинность."""
    row = await group_create(workspace_code=workspace.code, title="Зона", sort=900)

    assert (await group_update(row.code, sort=0)).sort == 0


async def test_soft_delete_hides_the_group_unless_asked_for(db, workspace):
    row = await group_create(workspace_code=workspace.code, title="Биллинг")

    assert await group_delete(row.code) is True

    assert await group_get(row.code) is None
    assert await group_list_by_workspace(workspace.code) == []
    assert len(await group_list_by_workspace(workspace.code, include_deleted=True)) == 1
    assert await group_restore(row.code) is True
    assert await group_get(row.code) is not None
