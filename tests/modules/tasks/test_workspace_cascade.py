"""What happens to groups and tasks when a workspace is deleted — and how they are counted.

Both questions live here, not in the ``workspace`` tests: the level 1 module knows nothing of our
tables and must not, while the cascade and the counters are behaviour on OUR side of the boundary.
There the mechanism is checked (a counter is declared — it arrives in the card), here what exactly
we put into that mechanism.

The workspace is created through the neighbouring module's CRUD: we have no endpoint of our own,
and bypassing it with a direct insert would test a path other than the one the app takes.
"""

from __future__ import annotations

import pytest

from src.modules.tasks.crud import group as group_crud
from src.modules.tasks.crud import task as task_crud
from src.modules.workspace.crud import workspace as workspace_crud

pytestmark = pytest.mark.db


async def _filled(db, title: str = "Работа"):
    """A workspace with one group and one task — the minimum that shows both cascade and count."""
    workspace = await workspace_crud.workspace_create(title=title)
    group = await group_crud.group_create(workspace_code=workspace.code, title="Биллинг")
    task = await task_crud.task_create(
        workspace_code=workspace.code, group_code=group.code, title="Счёт"
    )
    return workspace, group, task


# ── cascade ───────────────────────────────────────────────────────────────────


async def test_soft_delete_of_a_workspace_keeps_our_rows(db):
    """A soft delete is reversible without a trace: the group and task stay put with their links."""
    workspace, group, task = await _filled(db)

    await workspace_crud.workspace_delete(workspace.code)

    assert (await group_crud.group_get(group.code)) is not None
    assert (await task_crud.task_get(task.code)) is not None


async def test_purge_of_a_workspace_takes_our_rows_with_it(db):
    """A physical delete takes the contents via the FK cascade — nothing is left to bring back."""
    workspace, group, task = await _filled(db)

    await workspace_crud.workspace_delete(workspace.code, hard=True)

    assert (await group_crud.group_get(group.code, include_deleted=True)) is None
    assert (await task_crud.task_get(task.code, include_deleted=True)) is None


async def test_purge_leaves_the_neighbour_workspace_untouched(db):
    """The cascade follows the FK, not the whole table: the neighbouring workspace is unaffected."""
    doomed, _, _ = await _filled(db, "Под снос")
    _, kept_group, kept_task = await _filled(db, "Остаётся")

    await workspace_crud.workspace_delete(doomed.code, hard=True)

    assert (await group_crud.group_get(kept_group.code)) is not None
    assert (await task_crud.task_get(kept_task.code)) is not None


# ── counters the module hands to the workspace ────────────────────────────────


async def test_counters_see_only_live_rows(db):
    """A counter promises what the person will find inside: a deleted group does not count."""
    workspace, _, _ = await _filled(db)
    second = await group_crud.group_create(workspace_code=workspace.code, title="Вторая")
    await group_crud.group_delete(second.code)

    groups = await group_crud.group_count_by_workspace_codes([workspace.code])
    tasks = await task_crud.task_count_by_workspace_codes([workspace.code])

    assert (groups[workspace.code], tasks[workspace.code]) == (1, 1)


async def test_counters_do_not_leak_across_workspaces(db):
    """Counted by workspace code: a neighbouring workspace never leaks into the number."""
    mine, _, _ = await _filled(db)
    await _filled(db, "Личное")

    groups = await group_crud.group_count_by_workspace_codes([mine.code])

    assert groups[mine.code] == 1


async def test_counters_skip_a_workspace_without_rows(db):
    """An empty workspace is absent from the answer — the card-side assembly fills in the zero."""
    empty = await workspace_crud.workspace_create(title="Пустое")

    groups = await group_crud.group_count_by_workspace_codes([empty.code])

    assert groups == {}
