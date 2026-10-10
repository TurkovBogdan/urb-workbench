"""Task search through the agent's ``tasks_list`` — the second surface over the same query.

The CRUD side (Cyrillic case, scopes) is ``tests/modules/tasks/test_task_search.py``; this is the
agent's path to it, kept apart because it is a path of its own.
"""

from __future__ import annotations

import pytest

from src.modules.tasks.crud.task import task_create

pytestmark = pytest.mark.db


async def test_mcp_list_finds_cyrillic_regardless_of_case(call, workspace):
    """The agent's search goes to the same query — and handles case the same way.

    Kept apart from the CRUD test on purpose: the fix lives in ``task_list_by_workspace``, but
    two surfaces use it, and the second has its own path to it.
    """
    await call("workspace_use", workspace_code=workspace.code)
    await task_create(workspace_code=workspace.code, title="Панель фильтров")

    found = await call("tasks_list", query="ПАНЕЛЬ")

    assert [row["title"] for row in found["tasks"]] == ["Панель фильтров"]
