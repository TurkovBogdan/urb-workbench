"""workbench MCP: the layout — creating and editing groups, moving work between them.

What is checked is the reason the tools exist at all: the agent lays out the list under the
person's direction, and the boundaries that stay with the person are held by refusal, not by a
request in the description.

The workspace fence is not re-checked here for every tool — it is shared and covered by
``test_mcp_scope.py``; only those of its triggers that look different for a batch than for a
single call are brought here.
"""

from __future__ import annotations

import pytest
from fastmcp.exceptions import ToolError

from src.modules.tasks.constants import GROUP_DESCRIPTION_MAX
from src.modules.tasks.crud import group as group_crud
from src.modules.tasks.crud import task as task_crud
from src.modules.tasks.mcp.group import REGROUP_CAP
from src.modules.workspace.crud.workspace import workspace_create

pytestmark = pytest.mark.db


@pytest.fixture
async def bound(call, workspace):
    """A session already bound to a workspace: without it every tool answers "pick one"."""
    await call("workspace_use", workspace_code=workspace.code)
    return workspace


def _titles(answer) -> list[str]:
    return [row["title"] for row in answer["groups"]]


# ── create ────────────────────────────────────────────────────────────────────


async def test_create_answers_with_the_whole_layout(call, bound):
    """The answer is the layout, not a receipt: the same edit shifted the counters and order."""
    answer = await call("group_create", title="Биллинг", description="Тарифы и счета")

    assert _titles(answer) == ["Биллинг"]
    assert answer["workspace"] == f"WORKSPACE@{bound.code}"
    assert answer["groups"][0]["task_count"] == 0


async def test_create_refuses_a_name_already_taken(call, bound):
    """Two groups with one name split one body of work in half — the refusal names the holder."""
    await call("group_create", title="Биллинг", description="Тарифы")

    with pytest.raises(ToolError, match="already called"):
        await call("group_create", title="Биллинг", description="Ещё раз")


async def test_create_ignores_case_when_it_checks_the_name(call, bound):
    """Cyrillic and case: folding happens in Python, because SQLite folds only ASCII."""
    await call("group_create", title="Биллинг", description="Тарифы")

    with pytest.raises(ToolError, match="already called"):
        await call("group_create", title="биллинг", description="Ещё раз")


async def test_create_refuses_an_empty_title(call, bound):
    with pytest.raises(ToolError, match="needs a title"):
        await call("group_create", title="   ", description="Тарифы")


async def test_create_adds_at_the_end_by_default(call, bound):
    await call("group_create", title="Биллинг", description="Тарифы")
    answer = await call("group_create", title="Инфра", description="Железо")

    assert _titles(answer) == ["Биллинг", "Инфра"]


async def test_create_places_relative_to_a_neighbour(call, bound):
    first = await call("group_create", title="Биллинг", description="Тарифы")
    anchor = first["groups"][0]["code"]

    answer = await call(
        "group_create", title="Инфра", description="Железо", place_before=anchor
    )

    assert _titles(answer) == ["Инфра", "Биллинг"]


# ── a refusal on the position must leave no trace ─────────────────────────────
# Found by a run against the live server: placement is the tool's SECOND action, and while it
# was checked after the write, "didn't work" reached the agent with the group already created.
# It reads a refusal as "nothing happened" and creates the group again.


async def test_create_writes_nothing_when_the_anchor_is_not_there(call, bound):
    with pytest.raises(ToolError, match="not a live group"):
        await call(
            "group_create",
            title="Биллинг",
            description="Тарифы",
            place_after="TASKGROUP@" + "0" * 10,
        )

    assert _titles(await call("groups_list")) == []


async def test_create_writes_nothing_when_both_anchors_are_given(call, bound):
    existing = await group_crud.group_create(workspace_code=bound.code, title="Инфра")

    with pytest.raises(ToolError, match="exactly one"):
        await call(
            "group_create",
            title="Биллинг",
            description="Тарифы",
            place_after=f"TASKGROUP@{existing.code}",
            place_before=f"TASKGROUP@{existing.code}",
        )

    assert _titles(await call("groups_list")) == ["Инфра"]


async def test_create_writes_nothing_when_the_anchor_is_of_the_wrong_type(call, bound):
    with pytest.raises(ToolError, match="TASKGROUP@ code is expected"):
        await call(
            "group_create",
            title="Биллинг",
            description="Тарифы",
            place_after="TASK@" + "0" * 10,
        )

    assert _titles(await call("groups_list")) == []


async def test_update_changes_nothing_when_the_anchor_is_not_there(call, bound):
    """On update a half-apply is quieter: name saved, position not, yet the answer is a refusal."""
    group = await group_crud.group_create(workspace_code=bound.code, title="Биллинг")

    with pytest.raises(ToolError, match="not a live group"):
        await call(
            "group_update",
            group_code=f"TASKGROUP@{group.code}",
            title="Оплаты",
            place_after="TASKGROUP@" + "0" * 10,
        )

    assert _titles(await call("groups_list")) == ["Биллинг"]


async def test_update_refuses_the_group_as_its_own_anchor(call, bound):
    group = await group_crud.group_create(workspace_code=bound.code, title="Биллинг")

    with pytest.raises(ToolError, match="relative to itself"):
        await call(
            "group_update",
            group_code=f"TASKGROUP@{group.code}",
            title="Оплаты",
            place_before=f"TASKGROUP@{group.code}",
        )

    assert _titles(await call("groups_list")) == ["Биллинг"]


# ── update ────────────────────────────────────────────────────────────────────


async def test_update_renames_without_moving_the_work(call, bound):
    group = await group_crud.group_create(workspace_code=bound.code, title="Биллинг")
    task = await task_crud.task_create(
        workspace_code=bound.code, title="Счета", group_code=group.code
    )

    answer = await call("group_update", group_code=f"TASKGROUP@{group.code}", title="Оплаты")

    assert _titles(answer) == ["Оплаты"]
    assert (await task_crud.task_get(task.code)).group_code == group.code


async def test_a_code_under_the_retired_group_prefix_still_reaches_its_group(call, bound):
    """``GROUP@`` codes sit in journals and agents' notes from before the rename; they still work."""
    group = await group_crud.group_create(workspace_code=bound.code, title="Биллинг")

    answer = await call("group_update", group_code=f"GROUP@{group.code}", title="Оплаты")

    assert _titles(answer) == ["Оплаты"]
    assert answer["groups"][0]["code"] == f"TASKGROUP@{group.code}"


async def test_update_may_keep_its_own_name(call, bound):
    """The name-taken check must not catch the very group being edited."""
    group = await group_crud.group_create(workspace_code=bound.code, title="Биллинг")

    answer = await call(
        "group_update",
        group_code=f"TASKGROUP@{group.code}",
        title="Биллинг",
        description="Границы переписаны",
    )

    assert answer["groups"][0]["description"] == "Границы переписаны"


async def test_update_refuses_a_group_in_the_bin(call, bound):
    """Only the person may restore it — else the agent makes a second same-named group beside it."""
    group = await group_crud.group_create(workspace_code=bound.code, title="Биллинг")
    await group_crud.group_delete(group.code)

    with pytest.raises(ToolError, match="in the bin"):
        await call("group_update", group_code=f"TASKGROUP@{group.code}", title="Оплаты")


async def test_update_moves_the_group_under_its_anchor(call, bound):
    top = await group_crud.group_create(workspace_code=bound.code, title="Биллинг")
    await group_crud.group_create(workspace_code=bound.code, title="Интерфейс")
    last = await group_crud.group_create(workspace_code=bound.code, title="Инфра")

    answer = await call(
        "group_update", group_code=f"TASKGROUP@{last.code}", place_after=f"TASKGROUP@{top.code}"
    )

    assert _titles(answer) == ["Биллинг", "Инфра", "Интерфейс"]


# ── moving work ───────────────────────────────────────────────────────────────


async def test_regroup_files_a_batch_in_one_call(call, bound):
    group = await group_crud.group_create(workspace_code=bound.code, title="Биллинг")
    first = await task_crud.task_create(workspace_code=bound.code, title="Счета")
    second = await task_crud.task_create(workspace_code=bound.code, title="Тарифы")

    answer = await call(
        "tasks_regroup",
        group_code=f"TASKGROUP@{group.code}",
        task_codes=[f"TASK@{first.code}", f"TASK@{second.code}"],
    )

    assert answer["moved"] == 2
    assert answer["groups"][0]["task_count"] == 2


async def test_regroup_with_an_empty_group_unfiles(call, bound):
    group = await group_crud.group_create(workspace_code=bound.code, title="Биллинг")
    task = await task_crud.task_create(
        workspace_code=bound.code, title="Счета", group_code=group.code
    )

    answer = await call("tasks_regroup", group_code="", task_codes=[f"TASK@{task.code}"])

    assert answer["moved"] == 1
    assert answer["groups"][0]["task_count"] == 0
    assert (await task_crud.task_get(task.code)).group_code is None


async def test_regroup_refuses_the_whole_batch_and_names_every_fault(call, bound):
    """A partly moved batch looks like a moved one — hence "all or nothing"."""
    other = await workspace_create(title="Личное")
    group = await group_crud.group_create(workspace_code=bound.code, title="Биллинг")
    mine = await task_crud.task_create(workspace_code=bound.code, title="Счета")
    stranger = await task_crud.task_create(workspace_code=other.code, title="Ремонт")
    missing = "TASK@" + "0" * 10

    with pytest.raises(ToolError) as refusal:
        await call(
            "tasks_regroup",
            group_code=f"TASKGROUP@{group.code}",
            task_codes=[f"TASK@{mine.code}", f"TASK@{stranger.code}", missing],
        )

    message = str(refusal.value)
    assert "another workspace" in message and "not a live task" in message
    assert (await task_crud.task_get(mine.code)).group_code is None


async def test_regroup_refuses_an_empty_batch(call, bound):
    group = await group_crud.group_create(workspace_code=bound.code, title="Биллинг")

    with pytest.raises(ToolError, match="at least one"):
        await call("tasks_regroup", group_code=f"TASKGROUP@{group.code}", task_codes=[])


async def test_regroup_refuses_a_batch_past_the_cap(call, bound):
    """A read shows its cap in numbers; a write has to state it as a refusal."""
    group = await group_crud.group_create(workspace_code=bound.code, title="Биллинг")

    with pytest.raises(ToolError, match=str(REGROUP_CAP)):
        await call(
            "tasks_regroup",
            group_code=f"TASKGROUP@{group.code}",
            task_codes=[f"TASK@{'0' * 10}"] * (REGROUP_CAP + 1),
        )


async def test_regroup_takes_the_subtasks_along(call, bound):
    """A subtask is part of its epic and sits in its group: a moved epic takes it along."""
    group = await group_crud.group_create(workspace_code=bound.code, title="Биллинг")
    epic = await task_crud.task_create(workspace_code=bound.code, title="Тарификация")
    child = await task_crud.task_create(
        workspace_code=bound.code, title="Миграция", parent_code=epic.code
    )

    await call(
        "tasks_regroup", group_code=f"TASKGROUP@{group.code}", task_codes=[f"TASK@{epic.code}"]
    )

    assert (await task_crud.task_get(child.code)).group_code == group.code


async def test_regroup_refuses_a_subtask_named_without_its_parent(call, bound):
    """A subtask is not filed into another group — and not one row of the batch lands."""
    group = await group_crud.group_create(workspace_code=bound.code, title="Биллинг")
    epic = await task_crud.task_create(workspace_code=bound.code, title="Тарификация")
    child = await task_crud.task_create(
        workspace_code=bound.code, title="Миграция", parent_code=epic.code
    )
    loose = await task_crud.task_create(workspace_code=bound.code, title="Отдельная")

    with pytest.raises(ToolError, match=f"'{child.code}' \\(a subtask of '{epic.code}'\\)"):
        await call(
            "tasks_regroup",
            group_code=f"TASKGROUP@{group.code}",
            task_codes=[f"TASK@{loose.code}", f"TASK@{child.code}"],
        )

    assert (await task_crud.task_get(loose.code)).group_code is None
    assert (await task_crud.task_get(child.code)).group_code is None


async def test_regroup_takes_a_subtask_that_travels_with_its_parent(call, bound):
    group = await group_crud.group_create(workspace_code=bound.code, title="Биллинг")
    epic = await task_crud.task_create(workspace_code=bound.code, title="Тарификация")
    child = await task_crud.task_create(
        workspace_code=bound.code, title="Миграция", parent_code=epic.code
    )

    await call(
        "tasks_regroup",
        group_code=f"TASKGROUP@{group.code}",
        task_codes=[f"TASK@{child.code}", f"TASK@{epic.code}"],
    )

    assert (await task_crud.task_get(epic.code)).group_code == group.code
    assert (await task_crud.task_get(child.code)).group_code == group.code


async def test_regroup_refuses_a_code_of_the_wrong_type(call, bound):
    """A mixed-up argument is not "not found", and the refusal names both types."""
    group = await group_crud.group_create(workspace_code=bound.code, title="Биллинг")

    with pytest.raises(ToolError, match="TASK@ code is expected"):
        await call(
            "tasks_regroup",
            group_code=f"TASKGROUP@{group.code}",
            task_codes=[f"TASKGROUP@{group.code}"],
        )


# ── boundaries that stayed with the person ────────────────────────────────────


async def test_delete_still_refuses_a_group_and_names_what_to_do(call, bound):
    group = await group_crud.group_create(workspace_code=bound.code, title="Биллинг")

    with pytest.raises(ToolError, match="tasks_regroup"):
        await call("delete", code=f"TASKGROUP@{group.code}")


# ── description limit ─────────────────────────────────────────────────────────


@pytest.mark.parametrize("tool", ["group_create", "group_update"])
async def test_both_tools_state_the_description_limit_up_front(mcp, tool):
    """The agent learns the number from the schema, not from its first refusal."""
    tools = {t.name: t for t in await mcp.list_tools()}

    described = tools[tool].inputSchema["properties"]["description"]["description"]

    assert f"{GROUP_DESCRIPTION_MAX} characters" in described


async def test_create_refuses_a_long_description_and_creates_nothing(call, bound):
    with pytest.raises(ToolError, match=r"129 characters long, the limit is 128"):
        await call(
            "group_create", title="Биллинг", description="д" * (GROUP_DESCRIPTION_MAX + 1)
        )

    assert await group_crud.group_list_by_workspace(bound.code, include_deleted=True) == []


async def test_update_refuses_a_long_description_and_applies_nothing(call, bound):
    """Neither the title sent alongside nor the move: the refused call leaves the layout as it was."""
    top = await group_crud.group_create(workspace_code=bound.code, title="Биллинг")
    group = await group_crud.group_create(
        workspace_code=bound.code, title="Инфра", description="Железо"
    )

    with pytest.raises(ToolError, match="group description"):
        await call(
            "group_update",
            group_code=f"TASKGROUP@{group.code}",
            title="Сервера",
            description="д" * (GROUP_DESCRIPTION_MAX + 1),
            place_before=f"TASKGROUP@{top.code}",
        )

    rows = await group_crud.group_list_by_workspace(bound.code)
    assert [(r.title, r.description) for r in rows] == [("Биллинг", ""), ("Инфра", "Железо")]
