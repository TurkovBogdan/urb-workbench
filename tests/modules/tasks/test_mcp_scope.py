"""Резолвер забора: какому пространству принадлежит код.

У группы и задачи пространство лежит в своей же строке, у этапа и записи журнала — через
задачу. Ошибись здесь — и забор начнёт пропускать чужое именно на тех кодах, которые агент
получает чаще всего: этапы и журнал он читает постранично, а задачу открывает один раз.
"""

from __future__ import annotations

import pytest

from src.modules.tasks.constants import (
    GROUP_CODE_PREFIX,
    NOTE_CODE_PREFIX,
    NOTE_DECISION,
    STAGE_CODE_PREFIX,
    TASK_CODE_PREFIX,
    TYPE_EXTENDED,
    TYPE_STANDARD,
)
from src.modules.tasks.crud import group as group_crud
from src.modules.tasks.crud import note as note_crud
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


async def test_note_reaches_the_workspace_through_its_task(workspace):
    task = await task_crud.task_create(
        workspace_code=workspace.code, title="Счета", type=TYPE_STANDARD
    )
    note = await note_crud.note_create(
        task_code=task.code, type=NOTE_DECISION, title="Берём вариант Б"
    )

    assert await workspace_of(NOTE_CODE_PREFIX, note.code) == workspace.code


async def test_a_code_with_no_row_behind_it_is_not_the_fence_s_business(workspace):
    """«Не найдено» скажет сам инструмент — его формулировка точнее общей."""
    assert await workspace_of(TASK_CODE_PREFIX, "0" * 10) is None


async def test_a_type_this_module_does_not_own_is_refused(workspace):
    with pytest.raises(ValueError, match="not an entity of this module"):
        await workspace_of("SOURCE", "0" * 10)
