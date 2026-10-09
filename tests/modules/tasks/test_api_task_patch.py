"""``PATCH /tasks/{code}`` — a partial update: only the fields sent are changed.

The key property is not reverting someone else's edits: a page that saved one field must not
return the rest to the state it once loaded them in.
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
    # Meanwhile the "agent" edited the criteria — the page knows nothing about it.
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
    assert body["group_code"] == f"TASKGROUP@{group.code}"
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


async def test_patch_of_one_work_field_leaves_the_other_two(client):
    """The page saves one card at a time; the agent may have written the neighbours meanwhile."""
    _, task = await _task(plan="план агента", progress="- ход агента", result="итог агента")

    body = (await client.patch(f"{TASKS}/{task.code}", json={"progress": "- правка человека"})).json()

    assert (body["plan"], body["progress"], body["result"]) == (
        "план агента",
        "- правка человека",
        "итог агента",
    )


@pytest.mark.parametrize("field", ["plan", "progress", "result"])
async def test_patch_refuses_null_for_a_work_field(client, field):
    _, task = await _task(**{field: "было"})

    response = await client.patch(f"{TASKS}/{task.code}", json={field: None})

    assert response.status_code == 400
    assert getattr(await task_crud.task_get(task.code), field) == "было"


@pytest.mark.parametrize("field", ["plan", "progress", "result"])
async def test_patch_refuses_an_overlong_work_field_and_keeps_the_old(client, field):
    from src.modules.tasks import constants

    limit = getattr(constants, f"{field.upper()}_MAX")
    _, task = await _task(**{field: "было"})

    response = await client.patch(f"{TASKS}/{task.code}", json={field: "я" * (limit + 1)})

    assert response.status_code == 400
    assert getattr(await task_crud.task_get(task.code), field) == "было"


@pytest.mark.parametrize("method", ["post", "put", "patch"])
async def test_a_stale_client_sending_body_is_refused_not_ignored(client, method):
    """A page built before the rename still sends ``body``. Dropped silently, its plan edits
    would vanish while the save reads as done; refused, the stale page shows an error."""
    workspace, task = await _task(plan="план")
    payload = {"title": "Счёт", "body": "старый клиент"}
    if method == "post":
        response = await client.post(TASKS, json={"workspace": workspace.code, **payload})
    else:
        response = await getattr(client, method)(f"{TASKS}/{task.code}", json=payload)

    assert response.status_code == 422
    assert "body" in response.json()["fields"]
    assert (await task_crud.task_get(task.code)).plan == "план"
