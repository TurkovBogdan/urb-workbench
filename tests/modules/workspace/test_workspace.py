"""CRUD пространств: создание, чтение, правка и логическое удаление."""

from __future__ import annotations

import pytest

from src.modules.workspace.constants import CODE_LEN, DESCRIPTION_MAX, TITLE_MAX
from src.modules.workspace.crud.workspace import (
    workspace_create,
    workspace_delete,
    workspace_get,
    workspace_list,
    workspace_restore,
    workspace_update,
)

pytestmark = pytest.mark.db


async def test_create_fills_defaults(db):
    row = await workspace_create(title="Работа")

    assert len(row.code) == CODE_LEN
    assert (row.description, row.color, row.icon) == ("", "", "")
    assert row.deleted_at is None


async def test_list_orders_by_title(db):
    await workspace_create(title="Личное")
    await workspace_create(title="Автономия")

    assert [row.title for row in await workspace_list()] == ["Автономия", "Личное"]


async def test_update_changes_only_passed_fields(db):
    row = await workspace_create(title="Работа", description="о работе", icon="folder")

    updated = await workspace_update(row.code, title="Дело")

    assert (updated.title, updated.description, updated.icon) == (
        "Дело",
        "о работе",
        "folder",
    )


async def test_long_text_is_clipped_by_code_points(db):
    row = await workspace_create(
        title="я" * (TITLE_MAX + 50), description="ю" * (DESCRIPTION_MAX + 50)
    )

    assert len(row.title) == TITLE_MAX and row.title[-1] == "я"
    assert len(row.description) == DESCRIPTION_MAX


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
