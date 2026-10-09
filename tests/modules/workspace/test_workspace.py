"""Workspace CRUD: create, read, update and soft delete."""

from __future__ import annotations

from datetime import datetime

import pytest
from sqlalchemy import update

from src.core.database import write_scope

from src.modules.workspace.constants import (
    CODE_LEN,
    DESCRIPTION_MAX,
    SORT_DEFAULT,
    SORT_STEP,
    TITLE_MAX,
)
from src.modules.workspace.crud.workspace import (
    workspace_create,
    workspace_delete,
    workspace_get,
    workspace_list,
    workspace_reorder,
    workspace_restore,
    workspace_update,
)
from src.modules.workspace.models.workspace import Workspace

pytestmark = pytest.mark.db


async def test_create_fills_defaults(db):
    row = await workspace_create(title="Работа")

    assert len(row.code) == CODE_LEN
    assert (row.description, row.color, row.icon) == ("", "", "")
    assert row.deleted_at is None
    assert row.sort == SORT_DEFAULT


async def test_list_puts_the_bigger_sort_first(db):
    await workspace_create(title="Автономия", sort=100)
    await workspace_create(title="Личное", sort=900)

    assert [row.title for row in await workspace_list()] == ["Личное", "Автономия"]


async def test_list_orders_equal_sort_by_title(db):
    await workspace_create(title="Личное", sort=SORT_DEFAULT)
    await workspace_create(title="Автономия", sort=SORT_DEFAULT)

    assert [row.title for row in await workspace_list()] == ["Автономия", "Личное"]


async def test_create_without_sort_lands_at_the_end(db):
    """The default is "below all", not ``SORT_DEFAULT``: else a tiebreak would place the new one."""
    first = await workspace_create(title="Личное")
    second = await workspace_create(title="Автономия")

    assert [row.title for row in await workspace_list()] == ["Личное", "Автономия"]
    assert second.sort == first.sort - SORT_STEP


async def test_the_end_ignores_deleted_workspaces(db):
    """A deleted row is not in the list, so "below all" is measured against live ones only."""
    live = await workspace_create(title="Работа")
    gone = await workspace_create(title="Удалённое", sort=0)
    await workspace_delete(gone.code)

    row = await workspace_create(title="Личное")

    assert row.sort == live.sort - SORT_STEP


async def test_update_sort_zero_is_applied(db):
    """``0`` is a valid position: the condition checks ``is not None``, not truthiness."""
    row = await workspace_create(title="Работа", sort=900)

    assert (await workspace_update(row.code, sort=0)).sort == 0


async def test_update_without_sort_keeps_the_position(db):
    row = await workspace_create(title="Работа", sort=700)

    assert (await workspace_update(row.code, title="Дело")).sort == 700


async def test_update_changes_only_passed_fields(db):
    row = await workspace_create(title="Работа", description="о работе", icon="folder")

    updated = await workspace_update(row.code, title="Дело")

    assert (updated.title, updated.description, updated.icon) == (
        "Дело",
        "о работе",
        "folder",
    )


async def test_a_long_title_is_clipped_by_code_points(db):
    row = await workspace_create(title="я" * (TITLE_MAX + 50))

    assert len(row.title) == TITLE_MAX and row.title[-1] == "я"


def test_the_description_column_is_128_wide():
    assert Workspace.__table__.c.description.type.length == DESCRIPTION_MAX == 128


async def test_create_takes_a_description_exactly_at_the_limit(db):
    text = "ю" * DESCRIPTION_MAX

    row = await workspace_create(title="Работа", description=text)

    assert row.description == text


async def test_create_refuses_a_description_over_the_limit_and_writes_nothing(db):
    """Refused with the numbers, never cut: the end of a one-line description is its point."""
    with pytest.raises(ValueError, match=r"129 characters long, the limit is 128"):
        await workspace_create(title="Работа", description="ю" * (DESCRIPTION_MAX + 1))

    assert await workspace_list(include_deleted=True) == []


async def test_update_refuses_a_long_description_and_keeps_the_whole_card(db):
    """The title sent in the same call is not applied either: the update is one write or none."""
    row = await workspace_create(title="Работа", description="Старое")

    with pytest.raises(ValueError, match="workspace description"):
        await workspace_update(
            row.code, title="Дело", description="ю" * (DESCRIPTION_MAX + 1)
        )

    kept = await workspace_get(row.code)
    assert (kept.title, kept.description) == ("Работа", "Старое")


async def test_soft_delete_hides_the_row_unless_asked_for(db):
    row = await workspace_create(title="Работа")

    assert await workspace_delete(row.code) is True

    assert await workspace_get(row.code) is None
    assert await workspace_list() == []
    hidden = await workspace_get(row.code, include_deleted=True)
    assert hidden is not None and hidden.deleted_at is not None


async def test_restore_brings_the_row_back(db):
    row = await workspace_create(title="Работа")
    await workspace_delete(row.code)

    assert await workspace_restore(row.code) is True

    assert (await workspace_get(row.code)).deleted_at is None
    assert await workspace_restore(row.code) is False


async def test_hard_delete_removes_the_row_entirely(db):
    row = await workspace_create(title="Работа")

    assert await workspace_delete(row.code, hard=True) is True

    assert await workspace_get(row.code, include_deleted=True) is None


async def test_delete_of_a_missing_workspace_reports_false(db):
    assert await workspace_delete("0" * CODE_LEN) is False


# ── reorder ───────────────────────────────────────────────────────────────────


async def _three():
    """Работа, Личное, Архив — top to bottom, each created at the end of the list."""
    return [await workspace_create(title=title) for title in ("Работа", "Личное", "Архив")]


async def _titles() -> list[str]:
    return [row.title for row in await workspace_list()]


async def test_reorder_puts_the_workspace_under_its_anchor(db):
    work, personal, archive = await _three()

    await workspace_reorder(work.code, after=personal.code)

    assert await _titles() == ["Личное", "Работа", "Архив"]


async def test_reorder_puts_the_workspace_above_its_anchor(db):
    work, personal, archive = await _three()

    await workspace_reorder(archive.code, before=work.code)

    assert await _titles() == ["Архив", "Работа", "Личное"]


async def test_reorder_leaves_the_list_evenly_spaced(db):
    """Equal ``sort`` values get separated: the new order no longer depends on the title tie-break."""
    for title in ("Б", "А", "В"):
        await workspace_create(title=title, sort=SORT_DEFAULT)
    first, second, third = await workspace_list()

    await workspace_reorder(third.code, after=first.code)

    rows = await workspace_list()
    assert [row.title for row in rows] == ["А", "В", "Б"]
    assert [row.sort for row in rows] == [
        SORT_DEFAULT + 2 * SORT_STEP,
        SORT_DEFAULT + SORT_STEP,
        SORT_DEFAULT,
    ]


async def test_reorder_keeps_the_last_change_dates(db):
    """A position is not an edit: the list shows ``updated_at`` as "last change", and a drag must
    not stamp every renumbered row with "just now"."""
    work, personal, archive = await _three()
    # Back-dated: timestamps are stored to the second, so rows created a moment ago would match
    # "now" even if the reorder stamped them, and the test would pass for the wrong reason.
    long_ago = datetime(2026, 1, 1, 12, 0, 0)
    async with write_scope() as s:
        await s.execute(update(Workspace).values(updated_at=long_ago))

    await workspace_reorder(archive.code, before=work.code)

    assert {row.updated_at for row in await workspace_list()} == {long_ago}
    assert await _titles() == ["Архив", "Работа", "Личное"]


async def test_reorder_skips_deleted_workspaces(db):
    """A deleted row takes no place in the numbering: it is not in the list a person drags."""
    work, personal, archive = await _three()
    await workspace_delete(personal.code)

    await workspace_reorder(archive.code, before=work.code)

    assert await _titles() == ["Архив", "Работа"]
    kept = await workspace_get(personal.code, include_deleted=True)
    assert kept.sort == personal.sort


@pytest.mark.parametrize(
    ("after", "before"), [(None, None), ("x", "y")], ids=["neither", "both"]
)
async def test_reorder_needs_exactly_one_reference_point(db, after, before):
    work, *_ = await _three()

    with pytest.raises(ValueError, match="exactly one"):
        await workspace_reorder(work.code, after=after, before=before)


async def test_reorder_refuses_itself_as_the_anchor(db):
    work, *_ = await _three()

    with pytest.raises(ValueError, match="relative to itself"):
        await workspace_reorder(work.code, after=work.code)


async def test_reorder_refuses_a_deleted_anchor(db):
    work, personal, _ = await _three()
    await workspace_delete(personal.code)

    with pytest.raises(ValueError, match="does not exist"):
        await workspace_reorder(work.code, after=personal.code)


async def test_reorder_of_a_deleted_workspace_reports_none(db):
    work, personal, _ = await _three()
    await workspace_delete(work.code)

    assert await workspace_reorder(work.code, after=personal.code) is None
