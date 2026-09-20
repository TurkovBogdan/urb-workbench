"""Удаление задачи: каскад по ветке, восстановление по совпадающей отметке, ``include_deleted``."""

from __future__ import annotations

import pytest

from src.modules.tasks.crud.link import link_get
from src.modules.tasks.crud.task import (
    task_create,
    task_delete,
    task_get,
    task_list_by_parent,
    task_list_by_workspace,
    task_restore,
)

pytestmark = pytest.mark.db


async def _branch(workspace_code: str):
    """Ветка из трёх уровней: корень → ребёнок → внук."""
    root = await task_create(workspace_code=workspace_code, title="Эпик")
    child = await task_create(
        workspace_code=workspace_code, title="Задача", parent_code=root.code
    )
    grandchild = await task_create(
        workspace_code=workspace_code, title="Подзадача", parent_code=child.code
    )
    return root, child, grandchild


async def test_soft_delete_marks_the_whole_branch_with_one_stamp(db, workspace):
    root, child, grandchild = await _branch(workspace.code)

    assert await task_delete(root.code) is True

    rows = [
        await task_get(code, include_deleted=True)
        for code in (root.code, child.code, grandchild.code)
    ]
    assert all(row.deleted_at is not None for row in rows)
    assert len({row.deleted_at for row in rows}) == 1


async def test_deleted_tasks_vanish_from_listings_by_default(db, workspace):
    root, child, _ = await _branch(workspace.code)

    await task_delete(root.code)

    assert await task_list_by_workspace(workspace.code) == []
    assert len(await task_list_by_workspace(workspace.code, include_deleted=True)) == 3
    assert await task_get(child.code) is None
    assert await task_list_by_parent(root.code) == []
    assert len(await task_list_by_parent(root.code, include_deleted=True)) == 1


async def test_restore_lifts_exactly_the_tasks_that_went_down_together(db, workspace):
    """Потомок, удалённый раньше и отдельно, несёт свою отметку — и остаётся удалённым."""
    root, child, grandchild = await _branch(workspace.code)
    await task_delete(grandchild.code)

    await task_delete(root.code)
    assert await task_restore(root.code) is True

    assert await task_get(root.code) is not None
    assert await task_get(child.code) is not None
    assert await task_get(grandchild.code) is None


async def test_restore_of_a_live_task_reports_false(db, workspace):
    root, *_ = await _branch(workspace.code)

    assert await task_restore(root.code) is False


async def test_hard_delete_takes_the_branch_and_its_tree_rows(db, workspace):
    """Иначе потомки остались бы в базе без строки связи — невидимые из любого обхода."""
    root, child, grandchild = await _branch(workspace.code)

    assert await task_delete(root.code, hard=True) is True

    for code in (root.code, child.code, grandchild.code):
        assert await task_get(code, include_deleted=True) is None
        assert await link_get(code) is None


async def test_delete_of_a_missing_task_reports_false(db, workspace):
    assert await task_delete("0" * 10) is False
