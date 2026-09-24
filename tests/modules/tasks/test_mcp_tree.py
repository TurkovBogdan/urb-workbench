"""workbench MCP: перенос задачи в дереве через ``task_update(parent_code=…)``.

Правила дерева покрыты в ``test_task_tree.py`` на CRUD; здесь — то, что видит агент: параметр в
схеме, форма ответа, подсказка в отказе и забор пространства на новом родителе.
"""

from __future__ import annotations

import pytest
from fastmcp.exceptions import ToolError

from src.modules.tasks.constants import ACTOR_HUMAN
from src.modules.tasks.crud import group as group_crud
from src.modules.tasks.crud import link as link_crud
from src.modules.tasks.crud import task as task_crud
from src.modules.workspace.crud.workspace import workspace_create

pytestmark = pytest.mark.db


@pytest.fixture
async def bound(call, workspace):
    await call("workspace_use", workspace_code=workspace.code)
    return workspace


async def test_task_update_offers_parent_code(mcp):
    tools = {tool.name: tool for tool in await mcp.list_tools()}

    described = tools["task_update"].inputSchema["properties"]["parent_code"]["description"]

    assert "top-level task" in described


async def test_the_answer_shows_the_new_parent_and_the_group_it_took(call, bound):
    group = await group_crud.group_create(workspace_code=bound.code, title="Биллинг")
    epic = await task_crud.task_create(
        workspace_code=bound.code, title="Эпик", group_code=group.code
    )
    loose = await task_crud.task_create(workspace_code=bound.code, title="Отдельная")

    answer = await call(
        "task_update", task_code=f"TASK@{loose.code}", parent_code=f"TASK@{epic.code}"
    )

    assert answer["parent_code"] == f"TASK@{epic.code}"
    assert answer["group_code"] == f"GROUP@{group.code}"


async def test_an_empty_parent_code_makes_it_a_top_level_task(call, bound):
    epic = await task_crud.task_create(workspace_code=bound.code, title="Эпик")
    child = await task_crud.task_create(
        workspace_code=bound.code, title="Часть", parent_code=epic.code
    )

    answer = await call("task_update", task_code=f"TASK@{child.code}", parent_code="")

    assert answer["parent_code"] is None
    assert (await link_crud.link_get(child.code)).parent_code is None


async def test_the_refusal_tells_the_agent_to_move_the_subtasks_first(call, bound):
    target = await task_crud.task_create(workspace_code=bound.code, title="Куда")
    epic = await task_crud.task_create(workspace_code=bound.code, title="Эпик")
    await task_crud.task_create(workspace_code=bound.code, title="Часть", parent_code=epic.code)

    with pytest.raises(ToolError, match="Move its subtasks out first"):
        await call(
            "task_update", task_code=f"TASK@{epic.code}", parent_code=f"TASK@{target.code}"
        )

    assert (await link_crud.link_get(epic.code)).parent_code is None


async def test_a_parent_from_another_workspace_is_refused_by_the_fence(call, bound):
    other = await workspace_create(title="Личное")
    stranger = await task_crud.task_create(workspace_code=other.code, title="Чужая")
    loose = await task_crud.task_create(workspace_code=bound.code, title="Отдельная")

    with pytest.raises(ToolError, match="Личное"):
        await call(
            "task_update", task_code=f"TASK@{loose.code}", parent_code=f"TASK@{stranger.code}"
        )

    assert (await link_crud.link_get(loose.code)).parent_code is None


async def test_a_task_a_person_set_can_still_be_moved(call, bound):
    """Место в дереве — раскладка, а не постановка: запрет на бриф его не касается."""
    epic = await task_crud.task_create(workspace_code=bound.code, title="Эпик")
    theirs = await task_crud.task_create(
        workspace_code=bound.code, title="Поставил человек", created_by=ACTOR_HUMAN
    )

    answer = await call(
        "task_update", task_code=f"TASK@{theirs.code}", parent_code=f"TASK@{epic.code}"
    )

    assert answer["parent_code"] == f"TASK@{epic.code}"


@pytest.mark.parametrize(
    ("tool", "args"),
    [
        ("task_update", {"parent_code": "TASK@"}),
        ("task_update", {"group_code": "GROUP@"}),
        ("tasks_regroup", {"group_code": "GROUP@"}),
    ],
)
async def test_a_bare_prefix_is_refused_rather_than_read_as_clear(call, bound, tool, args):
    """«TASK@» без кода раньше доезжал до CRUD пустой строкой — и выносил подзадачу в корень."""
    group = await group_crud.group_create(workspace_code=bound.code, title="Биллинг")
    epic = await task_crud.task_create(
        workspace_code=bound.code, title="Эпик", group_code=group.code
    )
    child = await task_crud.task_create(
        workspace_code=bound.code, title="Часть", parent_code=epic.code
    )
    target = (
        {"task_codes": [f"TASK@{epic.code}"]}
        if tool == "tasks_regroup"
        else {"task_code": f"TASK@{child.code}"}
    )

    with pytest.raises(ToolError, match="is not a (TASK|GROUP)@ code"):
        await call(tool, **target, **args)

    assert (await link_crud.link_get(child.code)).parent_code == epic.code
    assert (await task_crud.task_get(child.code)).group_code == group.code
    assert (await task_crud.task_get(epic.code)).group_code == group.code


async def test_the_agent_cannot_reopen_a_subtask_of_a_closed_task(call, bound):
    epic = await task_crud.task_create(workspace_code=bound.code, title="Эпик")
    part = await task_crud.task_create(
        workspace_code=bound.code, title="Часть", parent_code=epic.code
    )
    await task_crud.task_update_status(part.code, "done")
    await task_crud.task_update_status(epic.code, "done")

    with pytest.raises(ToolError, match="Reopening .* is the person's call"):
        await call("task_status", task_code=f"TASK@{part.code}", status="in_progress")

    assert (await task_crud.task_get(part.code)).status == "done"


async def test_a_subtask_cannot_be_created_under_a_subtask(call, bound):
    epic = await task_crud.task_create(workspace_code=bound.code, title="Эпик")
    child = await task_crud.task_create(
        workspace_code=bound.code, title="Часть", parent_code=epic.code
    )

    with pytest.raises(ToolError, match="one level deep"):
        await call(
            "task_create",
            title="Часть части",
            description="Не заводится",
            parent_code=f"TASK@{child.code}",
        )

    assert len(await task_crud.task_list_by_workspace(bound.code)) == 2
