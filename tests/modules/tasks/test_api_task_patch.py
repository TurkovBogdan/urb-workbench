"""``PATCH /tasks/{code}`` — частичная правка: меняются только переданные поля.

Главное свойство — не откатывать чужое: страница, сохранившая одно поле, не должна вернуть
остальные к тому виду, в каком она их когда-то загрузила.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from src.modules.tasks.crud import group as group_crud
from src.modules.tasks.crud import task as task_crud
from src.modules.workspace.crud import workspace as workspace_crud

pytestmark = pytest.mark.db

TASKS = "/internal/workbench/tasks"


async def _task(**fields):
    workspace = await workspace_crud.workspace_create(title="Работа")
    return workspace, await task_crud.task_create(workspace_code=workspace.code, title="Счёт", **fields)


async def test_patch_changes_only_the_given_field(client):
    _, task = await _task(context="контекст", criteria="- критерий")
    # Параллельно «агент» поправил критерии — страница про это не знает.
    await task_crud.task_update(task.code, criteria="- критерий агента")

    body = (await client.patch(f"{TASKS}/{task.code}", json={"context": "новый контекст"})).json()

    assert body["context"] == "новый контекст"
    assert body["criteria"] == "- критерий агента"
    assert body["title"] == "Счёт"


async def test_patch_keeps_group_and_deadline_unless_named(client):
    workspace, task = await _task(deadline_at=datetime(2026, 9, 30, 18, 0, tzinfo=UTC))
    group = await group_crud.group_create(workspace_code=workspace.code, title="Оплаты")
    await task_crud.task_update(task.code, group_code=group.code)

    body = (await client.patch(f"{TASKS}/{task.code}", json={"priority": "high"})).json()

    assert body["priority"] == "high"
    assert body["group_code"] == f"GROUP@{group.code}"
    assert body["deadline_at"] is not None


async def test_patch_null_clears_group_and_deadline(client):
    workspace, task = await _task(deadline_at=datetime(2026, 9, 30, 18, 0, tzinfo=UTC))
    group = await group_crud.group_create(workspace_code=workspace.code, title="Оплаты")
    await task_crud.task_update(task.code, group_code=group.code)

    body = (
        await client.patch(f"{TASKS}/{task.code}", json={"group_code": None, "deadline_at": None})
    ).json()

    assert body["group_code"] is None
    assert body["deadline_at"] is None


async def test_patch_refuses_null_for_a_text_field(client):
    _, task = await _task(context="контекст")
    response = await client.patch(f"{TASKS}/{task.code}", json={"context": None})
    assert response.status_code == 400
    assert (await task_crud.task_get(task.code)).context == "контекст"


async def test_patch_refuses_an_empty_title(client):
    _, task = await _task()
    response = await client.patch(f"{TASKS}/{task.code}", json={"title": "   "})
    assert response.status_code == 422


async def test_patch_of_a_deleted_task_is_409(client):
    _, task = await _task()
    await task_crud.task_delete(task.code)
    response = await client.patch(f"{TASKS}/{task.code}", json={"context": "x"})
    assert response.status_code == 409
