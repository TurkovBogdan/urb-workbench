"""workbench MCP: choosing a workspace and the fence around it.

This checks the behaviour the server is built around: the workspace is named once, nobody passes
it after that, and a miss outside the boundary answers loudly and by name. There are no tests for
"sessions do not see each other" here — the in-memory client is blind to that, see
``test_mcp_session_http.py``.
"""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastmcp.exceptions import ToolError

from src.modules.tasks import TasksModule
from src.modules.tasks.crud import group as group_crud
from src.modules.tasks.crud import task as task_crud
from src.modules.workspace.crud.workspace import workspace_create
from src.modules.workspace.mcp.errors import NO_ACTIVE_WORKSPACE, WORKSPACE_MISMATCH

pytestmark = pytest.mark.db


@pytest.fixture
def counters(config):
    """Content counters are declared by ``configure()`` while the app is assembled — we call it.

    The registry is process-wide and its entries are overwritten by key, so there is nothing to
    clean up: the state after the fixture is exactly the same as after a normal app startup.
    """
    TasksModule().configure(FastAPI(), config)


async def test_list_marks_nothing_active_before_a_choice(call, workspace):
    """Before a choice none is active: the flag is the only way to see that."""
    rows = await call("workspaces_list")

    assert [row["active"] for row in rows["result"]] == [False]


async def test_list_carries_what_is_inside(call, workspace, counters):
    """Counters answer "which one holds the work" without opening each."""
    await group_crud.group_create(workspace_code=workspace.code, title="Биллинг")
    await task_crud.task_create(workspace_code=workspace.code, title="Счета")

    rows = await call("workspaces_list")

    assert rows["result"][0]["counters"] == {"groups": 1, "tasks": 1}


async def test_use_binds_and_the_list_then_shows_it(call, workspace):
    bound = await call("workspace_use", workspace_code=f"WORKSPACE@{workspace.code}")

    assert bound["active"] is True
    assert bound["code"] == f"WORKSPACE@{workspace.code}"
    rows = await call("workspaces_list")
    assert [row["active"] for row in rows["result"]] == [True]


async def test_a_lower_case_code_works_end_to_end_and_answers_in_upper_case(call, workspace):
    """An agent holding a code from before the switch is served as if it had sent the new one."""
    task = await task_crud.task_create(workspace_code=workspace.code, title="Счета")

    bound = await call("workspace_use", workspace_code=f"workspace@{workspace.code.lower()}")
    got = await call("task_get", task_code=f"task@{task.code.lower()}")

    assert bound["code"] == f"WORKSPACE@{workspace.code}"
    assert got["code"] == f"TASK@{task.code}"
    assert task.code == task.code.upper()


async def test_use_tells_how_long_the_choice_lasts(call, workspace):
    """The agent cannot infer the binding's lifetime — the answer states it, not the description."""
    bound = await call("workspace_use", workspace_code=workspace.code)

    assert "MCP_WORKSPACE" in bound["note"]
    assert f"WORKSPACE@{workspace.code}" in bound["note"]


async def test_use_refuses_a_workspace_that_is_not_there(call, db):
    with pytest.raises(ToolError, match="does not exist"):
        await call("workspace_use", workspace_code="WORKSPACE@" + "0" * 10)


async def test_bound_tool_refuses_before_a_workspace_is_chosen(call, workspace):
    """The refusal names BOTH tools: without the second the agent hunts for a nonexistent arg."""
    with pytest.raises(ToolError) as caught:
        await call("groups_list")

    assert "workspaces_list" in str(caught.value)
    assert "workspace_use" in str(caught.value)


async def test_bound_tool_takes_no_workspace_argument(mcp):
    """The argument is absent from the SCHEMA, not just the code: else the model invents it."""
    tools = {tool.name: tool for tool in await mcp.list_tools()}

    assert "workspace" not in str(tools["groups_list"].inputSchema.get("properties", {}))


async def test_groups_come_from_the_bound_workspace_only(call, workspace):
    other = await workspace_create(title="Личное")
    await group_crud.group_create(workspace_code=workspace.code, title="Биллинг")
    await group_crud.group_create(workspace_code=other.code, title="Ремонт")
    await call("workspace_use", workspace_code=workspace.code)

    answer = await call("groups_list")

    assert [group["title"] for group in answer["groups"]] == ["Биллинг"]


async def test_every_bound_answer_names_its_workspace(call, workspace):
    """The fourth lever: otherwise work in the wrong boundary looks just like an empty result."""
    await call("workspace_use", workspace_code=workspace.code)

    answer = await call("groups_list")

    assert answer["workspace"] == f"WORKSPACE@{workspace.code}"
    assert answer["workspace_title"] == "Работа"


async def test_a_code_from_another_workspace_is_refused_by_name(call, workspace):
    other = await workspace_create(title="Личное")
    stranger = await task_crud.task_create(workspace_code=other.code, title="Ремонт")
    await call("workspace_use", workspace_code=workspace.code)

    with pytest.raises(ToolError) as caught:
        await call("task_get", task_code=f"TASK@{stranger.code}")

    # Both titles, not just codes: codes are random and unreadable at a glance.
    assert "'Личное'" in str(caught.value) and "'Работа'" in str(caught.value)


async def test_a_task_of_the_bound_workspace_reads_fine(call, workspace):
    task = await task_crud.task_create(
        workspace_code=workspace.code, title="Счета", description="Чтобы выставлялись"
    )
    await call("workspace_use", workspace_code=workspace.code)

    row = await call("task_get", task_code=f"TASK@{task.code}")

    assert row["title"] == "Счета" and row["description"] == "Чтобы выставлялись"


async def test_no_agent_dto_leaks_its_prose_into_the_schema(mcp):
    """An agent DTO's docstring ends up in the tool schema and is paid for on every connection.

    That is why notes on agent contracts live as a comment ABOVE the class, not as a docstring.
    The rule is easy to break back — a class with a docstring looks tidier — and only this test
    can notice: no functional test turns red over an extra description.
    """
    for tool in await mcp.list_tools():
        schema = tool.outputSchema or {}
        assert "description" not in schema, f"{tool.name}: the response DTO carries a docstring"
        for name, nested in (schema.get("$defs") or {}).items():
            assert "description" not in nested, f"{tool.name}/{name}: a nested DTO has a docstring"


async def test_refusals_carry_their_rule_code():
    """Rule codes are a contract with the interface and tests: the phrase may change, the code
    may not."""
    assert NO_ACTIVE_WORKSPACE == "no_active_workspace"
    assert WORKSPACE_MISMATCH == "workspace_mismatch"
