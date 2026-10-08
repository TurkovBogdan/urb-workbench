"""The fence's resolver: which workspace a code belongs to.

A group and a task carry their workspace in their own row; a stage and a journal entry reach it
through the task. Get this wrong and the fence starts letting foreign data through on exactly the
codes the agent receives most often: it reads stages and the journal page by page, while it opens
a task once.
"""

from __future__ import annotations

import pytest

from src.modules.tasks.constants import (
    GROUP_CODE_PREFIX,
    JOURNAL_CODE_PREFIX,
    JOURNAL_DECISION,
    STAGE_CODE_PREFIX,
    TASK_CODE_PREFIX,
    TYPE_EXTENDED,
    TYPE_STANDARD,
)
from src.modules.tasks.crud import group as group_crud
from src.modules.tasks.crud import journal as journal_crud
from src.modules.tasks.crud import stage as stage_crud
from src.modules.tasks.crud import task as task_crud
from src.modules.tasks.mcp.scope import workspace_of

pytestmark = pytest.mark.db


async def test_group_points_at_its_own_workspace(workspace):
    group = await group_crud.group_create(workspace_code=workspace.code, title="Биллинг")

    assert await workspace_of(GROUP_CODE_PREFIX, group.code) == workspace.code


async def test_task_points_at_its_own_workspace(workspace):
    task = await task_crud.task_create(workspace_code=workspace.code, title="Счета")

    assert await workspace_of(TASK_CODE_PREFIX, task.code) == workspace.code


async def test_stage_reaches_the_workspace_through_its_task(workspace):
    task = await task_crud.task_create(
        workspace_code=workspace.code, title="Счета", type=TYPE_EXTENDED
    )
    stage = await stage_crud.stage_create(task_code=task.code, title="Схема")

    assert await workspace_of(STAGE_CODE_PREFIX, stage.code) == workspace.code


async def test_a_journal_entry_reaches_the_workspace_through_its_task(workspace):
    task = await task_crud.task_create(
        workspace_code=workspace.code, title="Счета", type=TYPE_STANDARD
    )
    entry = await journal_crud.journal_create(
        task_code=task.code, type=JOURNAL_DECISION, title="Берём вариант Б"
    )

    assert await workspace_of(JOURNAL_CODE_PREFIX, entry.code) == workspace.code


async def test_a_code_with_no_row_behind_it_is_not_the_fence_s_business(workspace):
    """The tool itself says "not found" — its wording is more precise than a generic one."""
    assert await workspace_of(TASK_CODE_PREFIX, "0" * 10) is None


async def test_a_type_this_module_does_not_own_is_refused(workspace):
    with pytest.raises(ValueError, match="not an entity of this module"):
        await workspace_of("SOURCE", "0" * 10)
