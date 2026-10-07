"""Group CRUD: belonging to a workspace, list order and soft deletion."""

from __future__ import annotations

import pytest

from src.modules.tasks.constants import CODE_LEN, GROUP_DESCRIPTION_MAX, SORT_DEFAULT
from src.modules.tasks.models.group import TasksGroup
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
    """A deleted workspace does not exist for the rest of the code — no place for a group there."""
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
    """The default is "below all", not ``SORT_DEFAULT``: else a tiebreak would place the new one."""
    await group_create(workspace_code=workspace.code, title="Биллинг")
    await group_create(workspace_code=workspace.code, title="Аудит")

    titles = [row.title for row in await group_list_by_workspace(workspace.code)]

    assert titles == ["Биллинг", "Аудит"]


async def test_find_by_title_ignores_case(db, workspace):
    row = await group_create(workspace_code=workspace.code, title="Биллинг")

    assert (await group_find_by_title(workspace.code, "  биллинг ")).code == row.code


async def test_find_by_title_skips_the_deleted_and_the_neighbours(db, workspace):
    """A title counts as taken only by a live group in the same workspace."""
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
    """Renumbering covers the whole list top to bottom: the order survives a used-up gap."""
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
    """``0`` is a valid position: the condition checks ``is not None``, not truthiness."""
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


# ── description limit ─────────────────────────────────────────────────────────


def test_description_column_is_as_wide_as_the_limit():
    """The model, the migration and every surface read one constant; the column is its mirror."""
    assert TasksGroup.__table__.c.description.type.length == GROUP_DESCRIPTION_MAX == 128


async def test_create_takes_a_description_exactly_at_the_limit(db, workspace):
    text = "д" * GROUP_DESCRIPTION_MAX

    row = await group_create(workspace_code=workspace.code, title="Зона", description=text)

    assert row.description == text


async def test_create_refuses_a_description_over_the_limit_and_writes_nothing(db, workspace):
    """Refused with the numbers, never cut: a clipped boundary reads as a different boundary."""
    with pytest.raises(ValueError, match=r"129 characters long, the limit is 128"):
        await group_create(
            workspace_code=workspace.code,
            title="Зона",
            description="д" * (GROUP_DESCRIPTION_MAX + 1),
        )

    assert await group_list_by_workspace(workspace.code, include_deleted=True) == []


async def test_update_refuses_a_long_description_and_keeps_the_whole_card(db, workspace):
    """The title sent in the same call is not applied either: the update is one write or none."""
    row = await group_create(workspace_code=workspace.code, title="Зона", description="Старое")

    with pytest.raises(ValueError, match="group description"):
        await group_update(
            row.code, title="Новое имя", description="д" * (GROUP_DESCRIPTION_MAX + 1)
        )

    kept = await group_get(row.code)
    assert (kept.title, kept.description) == ("Зона", "Старое")
