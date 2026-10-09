"""The task tree: one level of nesting, and a subtask's group is its parent's group.

CRUD enforces the rules, so they are the same for MCP and REST. Every refusal is checked against
the data, not only the text: a move and a card edit run in one transaction, and a refusal must
roll back both halves.
"""

from __future__ import annotations

import pytest
from sqlalchemy import update

from src.core.database import write_scope
from src.modules.tasks.constants import SORT_STEP, STATUS_CANCELED, STATUS_DONE
from src.core.utils.date import utc_now
from src.modules.tasks.crud.group import group_create
from src.modules.tasks.models.group import TasksGroup
from src.modules.tasks.crud.link import link_get, link_move
from src.modules.tasks.crud.task import (
    task_create,
    task_delete,
    task_get,
    task_list_by_workspace,
    task_regroup,
    task_update,
    task_update_status,
)
from src.modules.tasks.models.task import TasksTask

pytestmark = pytest.mark.db


async def _misfile(code: str, group_code: str | None) -> None:
    """Split a subtask's group from its parent's — the way the data lay before the rule."""
    async with write_scope() as s:
        await s.execute(
            update(TasksTask).where(TasksTask.code == code).values(group_code=group_code)
        )


# ── creation ──────────────────────────────────────────────────────────────────


async def test_a_subtask_takes_its_parents_group(db, workspace):
    group = await group_create(workspace_code=workspace.code, title="Биллинг")
    parent = await task_create(
        workspace_code=workspace.code, title="Эпик", group_code=group.code
    )

    child = await task_create(
        workspace_code=workspace.code, title="Часть", parent_code=parent.code
    )

    assert child.group_code == group.code


async def test_a_subtask_with_another_group_is_refused(db, workspace):
    billing = await group_create(workspace_code=workspace.code, title="Биллинг")
    interface = await group_create(workspace_code=workspace.code, title="Интерфейс")
    parent = await task_create(
        workspace_code=workspace.code, title="Эпик", group_code=billing.code
    )

    with pytest.raises(ValueError, match="sits in its parent's group"):
        await task_create(
            workspace_code=workspace.code,
            title="Часть",
            parent_code=parent.code,
            group_code=interface.code,
        )

    assert len(await task_list_by_workspace(workspace.code)) == 1


async def test_a_subtask_of_a_subtask_is_not_created(db, workspace):
    root = await task_create(workspace_code=workspace.code, title="Эпик")
    child = await task_create(
        workspace_code=workspace.code, title="Часть", parent_code=root.code
    )

    with pytest.raises(ValueError, match=f"itself a subtask of '{root.code}'"):
        await task_create(
            workspace_code=workspace.code, title="Часть части", parent_code=child.code
        )

    assert len(await task_list_by_workspace(workspace.code)) == 2


# ── move: a task becomes a subtask ────────────────────────────────────────────


async def test_moving_under_a_parent_takes_its_group_and_the_end_of_its_row(db, workspace):
    billing = await group_create(workspace_code=workspace.code, title="Биллинг")
    interface = await group_create(workspace_code=workspace.code, title="Интерфейс")
    parent = await task_create(
        workspace_code=workspace.code, title="Эпик", group_code=billing.code
    )
    settled = await task_create(
        workspace_code=workspace.code, title="Уже там", parent_code=parent.code
    )
    moved = await task_create(
        workspace_code=workspace.code, title="Переезжает", group_code=interface.code
    )

    row = await task_update(moved.code, parent_code=parent.code)

    assert row.group_code == billing.code
    link = await link_get(moved.code)
    assert link.parent_code == parent.code
    assert link.sort == (await link_get(settled.code)).sort - SORT_STEP


async def test_a_subtask_moves_to_another_parent(db, workspace):
    first = await task_create(workspace_code=workspace.code, title="Первый эпик")
    second = await task_create(workspace_code=workspace.code, title="Второй эпик")
    child = await task_create(
        workspace_code=workspace.code, title="Часть", parent_code=first.code
    )

    await task_update(child.code, parent_code=second.code)

    assert (await link_get(child.code)).parent_code == second.code


async def test_a_task_with_subtasks_cannot_become_one(db, workspace):
    """The refusal names the subtasks and says what to do first."""
    target = await task_create(workspace_code=workspace.code, title="Куда")
    epic = await task_create(workspace_code=workspace.code, title="Эпик")
    child = await task_create(
        workspace_code=workspace.code, title="Часть", parent_code=epic.code
    )

    with pytest.raises(ValueError, match=f"'{child.code}'.*Move its subtasks out first"):
        await task_update(epic.code, parent_code=target.code)

    assert (await link_get(epic.code)).parent_code is None


async def test_a_subtask_in_the_bin_also_holds_its_parent_in_place(db, workspace):
    """Restoring it would put it back under the moved parent — as a second level."""
    target = await task_create(workspace_code=workspace.code, title="Куда")
    epic = await task_create(workspace_code=workspace.code, title="Эпик")
    child = await task_create(
        workspace_code=workspace.code, title="Часть", parent_code=epic.code
    )
    await task_delete(child.code)

    with pytest.raises(ValueError, match=f"'{child.code}' \\(in the bin\\).*purged"):
        await task_update(epic.code, parent_code=target.code)

    assert (await link_get(epic.code)).parent_code is None


async def test_a_subtask_is_not_a_parent(db, workspace):
    root = await task_create(workspace_code=workspace.code, title="Эпик")
    child = await task_create(
        workspace_code=workspace.code, title="Часть", parent_code=root.code
    )
    loose = await task_create(workspace_code=workspace.code, title="Отдельная")

    with pytest.raises(ValueError, match=f"Put the task under '{root.code}' instead"):
        await task_update(loose.code, parent_code=child.code)

    assert (await link_get(loose.code)).parent_code is None


@pytest.mark.parametrize("state", ["deleted", "done"])
async def test_a_parent_in_the_bin_or_closed_is_refused(db, workspace, state):
    parent = await task_create(workspace_code=workspace.code, title="Эпик")
    loose = await task_create(workspace_code=workspace.code, title="Отдельная")
    if state == "deleted":
        await task_delete(parent.code)
    else:
        await task_update_status(parent.code, STATUS_DONE)

    with pytest.raises(ValueError, match="deleted|takes no new open parts"):
        await task_update(loose.code, parent_code=parent.code)

    assert (await link_get(loose.code)).parent_code is None


@pytest.mark.parametrize("closed", [STATUS_DONE, STATUS_CANCELED])
async def test_a_closed_task_may_go_under_a_closed_parent(db, workspace, closed):
    """Sorting finished work under an epic is tidying history, not new work."""
    parent = await task_create(workspace_code=workspace.code, title="Эпик")
    finished = await task_create(workspace_code=workspace.code, title="Сделанная")
    await task_update_status(parent.code, closed)
    await task_update_status(finished.code, STATUS_DONE)

    await task_update(finished.code, parent_code=parent.code)

    assert (await link_get(finished.code)).parent_code == parent.code


async def test_an_open_subtask_is_not_created_under_a_closed_parent(db, workspace):
    parent = await task_create(workspace_code=workspace.code, title="Эпик")
    await task_update_status(parent.code, STATUS_DONE)

    with pytest.raises(ValueError, match="takes no new open parts"):
        await task_create(
            workspace_code=workspace.code, title="Новая часть", parent_code=parent.code
        )

    assert len(await task_list_by_workspace(workspace.code)) == 1


async def test_a_closed_subtask_is_created_under_a_closed_parent(db, workspace):
    """The person records after the fact what is already done: the form sets the status at once."""
    parent = await task_create(workspace_code=workspace.code, title="Эпик")
    await task_update_status(parent.code, STATUS_DONE)

    child = await task_create(
        workspace_code=workspace.code,
        title="Сделанная часть",
        parent_code=parent.code,
        status=STATUS_DONE,
    )

    assert (await link_get(child.code)).parent_code == parent.code


async def test_a_refused_move_rolls_back_the_card_edit_of_the_same_call(db, workspace):
    """Otherwise the agent reads the refusal as "nothing happened" while the title is already
    rewritten."""
    root = await task_create(workspace_code=workspace.code, title="Эпик")
    child = await task_create(
        workspace_code=workspace.code, title="Часть", parent_code=root.code
    )
    loose = await task_create(workspace_code=workspace.code, title="Прежний заголовок")

    with pytest.raises(ValueError):
        await task_update(loose.code, title="Новый заголовок", parent_code=child.code)

    assert (await task_get(loose.code)).title == "Прежний заголовок"


async def test_moving_under_a_parent_with_a_foreign_group_is_refused(db, workspace):
    billing = await group_create(workspace_code=workspace.code, title="Биллинг")
    interface = await group_create(workspace_code=workspace.code, title="Интерфейс")
    parent = await task_create(
        workspace_code=workspace.code, title="Эпик", group_code=billing.code
    )
    loose = await task_create(workspace_code=workspace.code, title="Отдельная")

    # The task is not a subtask yet — the refusal talks about a move, not "leaving the branch".
    with pytest.raises(ValueError, match=f"Moving '{loose.code}' under .*Leave group_code out"):
        await task_update(loose.code, parent_code=parent.code, group_code=interface.code)

    assert (await link_get(loose.code)).parent_code is None
    assert (await task_get(loose.code)).group_code is None


async def test_naming_the_current_parent_moves_nothing(db, workspace):
    """Repeating a move already made does not send the task to the end of the row."""
    root = await task_create(workspace_code=workspace.code, title="Эпик")
    first = await task_create(
        workspace_code=workspace.code, title="Первая", parent_code=root.code
    )
    await task_create(workspace_code=workspace.code, title="Вторая", parent_code=root.code)
    before = (await link_get(first.code)).sort

    await task_update(first.code, parent_code=root.code)

    assert (await link_get(first.code)).sort == before


async def test_a_parent_filed_under_a_deleted_group_takes_no_subtasks(db, workspace):
    """The subtask would get a deleted group's code and vanish from the list — a refusal instead.

    ``group_delete`` no longer leaves tasks in a deleted group, but data written before it did
    still can hold that state; it is set up directly here, the way such a row exists.
    """
    group = await group_create(workspace_code=workspace.code, title="Биллинг")
    parent = await task_create(
        workspace_code=workspace.code, title="Эпик", group_code=group.code
    )
    loose = await task_create(workspace_code=workspace.code, title="Отдельная")
    async with write_scope() as s:
        await s.execute(
            update(TasksGroup).where(TasksGroup.code == group.code).values(deleted_at=utc_now())
        )

    with pytest.raises(ValueError, match="does not exist \\(or is deleted\\).*Refile"):
        await task_update(loose.code, parent_code=parent.code)
    with pytest.raises(ValueError, match="does not exist \\(or is deleted\\).*Refile"):
        await task_create(workspace_code=workspace.code, title="Часть", parent_code=parent.code)

    assert (await link_get(loose.code)).parent_code is None
    assert (await task_get(loose.code)).group_code is None
    assert len(await task_list_by_workspace(workspace.code)) == 2


# ── move: a subtask goes up to the root ───────────────────────────────────────


async def test_leaving_the_branch_keeps_the_group_of_the_former_parent(db, workspace):
    group = await group_create(workspace_code=workspace.code, title="Биллинг")
    parent = await task_create(
        workspace_code=workspace.code, title="Эпик", group_code=group.code
    )
    child = await task_create(
        workspace_code=workspace.code, title="Часть", parent_code=parent.code
    )

    row = await task_update(child.code, parent_code="")

    assert row.group_code == group.code
    link = await link_get(child.code)
    assert link.parent_code is None
    assert link.sort == (await link_get(parent.code)).sort - SORT_STEP


async def test_leaving_the_branch_into_another_group_is_one_call(db, workspace):
    billing = await group_create(workspace_code=workspace.code, title="Биллинг")
    interface = await group_create(workspace_code=workspace.code, title="Интерфейс")
    parent = await task_create(
        workspace_code=workspace.code, title="Эпик", group_code=billing.code
    )
    child = await task_create(
        workspace_code=workspace.code, title="Часть", parent_code=parent.code
    )

    row = await task_update(child.code, parent_code="", group_code=interface.code)

    assert row.group_code == interface.code
    assert (await link_get(child.code)).parent_code is None


# ── a subtask's group ─────────────────────────────────────────────────────────


async def test_a_subtask_is_not_refiled_on_its_own(db, workspace):
    billing = await group_create(workspace_code=workspace.code, title="Биллинг")
    interface = await group_create(workspace_code=workspace.code, title="Интерфейс")
    parent = await task_create(
        workspace_code=workspace.code, title="Эпик", group_code=billing.code
    )
    child = await task_create(
        workspace_code=workspace.code, title="Часть", parent_code=parent.code
    )

    with pytest.raises(ValueError, match=f"File '{parent.code}' instead"):
        await task_update(child.code, group_code=interface.code)

    assert (await task_get(child.code)).group_code == billing.code


async def test_a_misfiled_subtask_can_go_back_to_its_parents_group(db, workspace):
    """Data from before the rule: a subtask in a foreign group goes back to its parent's."""
    billing = await group_create(workspace_code=workspace.code, title="Биллинг")
    interface = await group_create(workspace_code=workspace.code, title="Интерфейс")
    parent = await task_create(
        workspace_code=workspace.code, title="Эпик", group_code=billing.code
    )
    child = await task_create(
        workspace_code=workspace.code, title="Часть", parent_code=parent.code
    )
    await _misfile(child.code, interface.code)

    await task_update(child.code, group_code=billing.code)

    assert (await task_get(child.code)).group_code == billing.code


async def test_refiling_a_parent_takes_every_subtask_along_the_binned_too(db, workspace):
    group = await group_create(workspace_code=workspace.code, title="Биллинг")
    parent = await task_create(workspace_code=workspace.code, title="Эпик")
    live = await task_create(
        workspace_code=workspace.code, title="Живая", parent_code=parent.code
    )
    binned = await task_create(
        workspace_code=workspace.code, title="В корзине", parent_code=parent.code
    )
    await task_delete(binned.code)

    await task_update(parent.code, group_code=group.code)

    assert (await task_get(live.code)).group_code == group.code
    assert (await task_get(binned.code, include_deleted=True)).group_code == group.code


async def test_regroup_returns_a_misfiled_subtask_to_its_parents_group(db, workspace):
    billing = await group_create(workspace_code=workspace.code, title="Биллинг")
    interface = await group_create(workspace_code=workspace.code, title="Интерфейс")
    parent = await task_create(
        workspace_code=workspace.code, title="Эпик", group_code=billing.code
    )
    child = await task_create(
        workspace_code=workspace.code, title="Часть", parent_code=parent.code
    )
    await _misfile(child.code, interface.code)

    await task_regroup([child.code], billing.code)

    assert (await task_get(child.code)).group_code == billing.code


# ── a closed task holds no open parts ─────────────────────────────────────────


@pytest.mark.parametrize("closed", [STATUS_DONE, STATUS_CANCELED])
async def test_a_task_with_open_subtasks_is_not_closed(db, workspace, closed):
    epic = await task_create(workspace_code=workspace.code, title="Эпик")
    open_part = await task_create(
        workspace_code=workspace.code, title="Открытая часть", parent_code=epic.code
    )
    finished = await task_create(
        workspace_code=workspace.code, title="Сделанная часть", parent_code=epic.code
    )
    await task_update_status(finished.code, STATUS_DONE)

    with pytest.raises(ValueError, match=f"'{open_part.code}' \\(backlog\\)"):
        await task_update_status(epic.code, closed)

    assert (await task_get(epic.code)).status == "backlog"


async def test_a_task_closes_once_every_subtask_is_closed(db, workspace):
    epic = await task_create(workspace_code=workspace.code, title="Эпик")
    done_part = await task_create(
        workspace_code=workspace.code, title="Сделана", parent_code=epic.code
    )
    dropped_part = await task_create(
        workspace_code=workspace.code, title="Отменена", parent_code=epic.code
    )
    await task_update_status(done_part.code, STATUS_DONE)
    await task_update_status(dropped_part.code, STATUS_CANCELED)

    assert (await task_update_status(epic.code, STATUS_DONE)).status == STATUS_DONE


async def test_a_subtask_of_a_closed_task_is_not_reopened(db, workspace):
    """What to do with a closed parent is the person's decision — hence a refusal, not a
    cascade."""
    epic = await task_create(workspace_code=workspace.code, title="Эпик")
    part = await task_create(
        workspace_code=workspace.code, title="Часть", parent_code=epic.code
    )
    await task_update_status(part.code, STATUS_DONE)
    await task_update_status(epic.code, STATUS_DONE)

    with pytest.raises(ValueError, match="the person's call"):
        await task_update_status(part.code, "in_progress")

    assert (await task_get(part.code)).status == STATUS_DONE
    assert (await task_get(epic.code)).status == STATUS_DONE


async def test_a_subtask_reopens_after_its_parent_does(db, workspace):
    epic = await task_create(workspace_code=workspace.code, title="Эпик")
    part = await task_create(
        workspace_code=workspace.code, title="Часть", parent_code=epic.code
    )
    await task_update_status(part.code, STATUS_DONE)
    await task_update_status(epic.code, STATUS_DONE)

    await task_update_status(epic.code, "in_progress")

    assert (await task_update_status(part.code, "in_progress")).status == "in_progress"


# ── the REST move path ────────────────────────────────────────────────────────


async def test_link_move_refuses_a_parent_in_the_bin(db, workspace):
    """Only existence used to be checked: the task moved under a deleted one and vanished."""
    parent = await task_create(workspace_code=workspace.code, title="Эпик")
    loose = await task_create(workspace_code=workspace.code, title="Отдельная")
    await task_delete(parent.code)

    with pytest.raises(ValueError, match="does not exist \\(or is deleted\\)"):
        await link_move(loose.code, parent_code=parent.code)

    assert (await link_get(loose.code)).parent_code is None


async def test_link_move_gives_the_subtask_its_parents_group(db, workspace):
    group = await group_create(workspace_code=workspace.code, title="Биллинг")
    parent = await task_create(
        workspace_code=workspace.code, title="Эпик", group_code=group.code
    )
    loose = await task_create(workspace_code=workspace.code, title="Отдельная")

    await link_move(loose.code, parent_code=parent.code)

    assert (await task_get(loose.code)).group_code == group.code
