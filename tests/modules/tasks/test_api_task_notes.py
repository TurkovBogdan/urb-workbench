"""HTTP API of task notes: what the task page does with them — add, open, edit, delete, reorder.

Every refusal is checked by the state after it: the page shows what the database holds, and a
refusal that half-wrote would show a change the person was told did not happen.
"""

from __future__ import annotations

import pytest

from src.modules.notes.crud import note as notes_crud
from src.modules.tasks.crud import note as note_crud
from src.modules.tasks.crud import task as task_crud
from src.modules.workspace.crud import workspace as workspace_crud

pytestmark = pytest.mark.db

TASKS = "/internal/workbench/tasks"


@pytest.fixture
async def task():
    workspace = await workspace_crud.workspace_create(title="Работа")
    return await task_crud.task_create(workspace_code=workspace.code, title="Тарифы")


async def _order(task_code: str) -> list[str]:
    return [note.code for note in await note_crud.task_note_list(task_code)]


async def test_a_note_is_added_at_the_end_and_listed_by_the_task(client, task):
    first = await note_crud.task_note_add(task_code=task.code, title="Схема")

    response = await client.post(f"{TASKS}/{task.code}/notes", json={"title": "Новая заметка"})

    assert response.status_code == 201, response.text
    created = response.json()
    assert created["code"].startswith("NOTE@") and created["task_code"] == f"TASK@{task.code}"
    assert created["body"] == ""
    listed = (await client.get(f"{TASKS}/{task.code}")).json()["notes"]
    assert [n["code"] for n in listed] == [f"NOTE@{first.code}", created["code"]]


async def test_a_blank_title_is_refused_and_nothing_is_created(client, task):
    response = await client.post(f"{TASKS}/{task.code}/notes", json={"title": "   "})

    assert response.status_code == 422
    assert await _order(task.code) == []


async def test_a_note_opens_whole_by_codes_in_any_case(client, task):
    note = await note_crud.task_note_add(task_code=task.code, title="Схема", body="# Текст")

    response = await client.get(f"{TASKS}/task@{task.code.lower()}/notes/note@{note.code.lower()}")

    assert response.status_code == 200, response.text
    body = response.json()
    assert (body["code"], body["title"], body["body"]) == (f"NOTE@{note.code}", "Схема", "# Текст")


async def test_a_note_of_another_task_is_not_found_here(client, task):
    other = await task_crud.task_create(workspace_code=task.workspace_code, title="Другая")
    foreign = await note_crud.task_note_add(task_code=other.code, title="Чужая")

    for response in (
        await client.get(f"{TASKS}/{task.code}/notes/{foreign.code}"),
        await client.patch(f"{TASKS}/{task.code}/notes/{foreign.code}", json={"title": "Моя"}),
        await client.delete(f"{TASKS}/{task.code}/notes/{foreign.code}"),
    ):
        assert (response.status_code, response.json()["code"]) == (404, "tasks.note.not_found")

    stored = await notes_crud.note_get(foreign.code)
    assert (stored.title, stored.deleted_at) == ("Чужая", None)


async def test_a_patch_changes_only_what_it_names(client, task):
    note = await note_crud.task_note_add(
        task_code=task.code, title="Схема", description="Когда", body="агент написал"
    )

    response = await client.patch(f"{TASKS}/{task.code}/notes/{note.code}", json={"title": "Схема v2"})

    assert response.status_code == 200, response.text
    stored = await notes_crud.note_get(note.code)
    assert (stored.title, stored.description, stored.body) == ("Схема v2", "Когда", "агент написал")


async def test_a_deleted_task_s_notes_open_but_take_no_change(client, task):
    note = await note_crud.task_note_add(task_code=task.code, title="Схема", body="текст")
    await task_crud.task_delete(task.code)
    path = f"{TASKS}/{task.code}/notes"

    assert (await client.get(f"{path}/{note.code}")).json()["body"] == "текст"
    for response in (
        await client.patch(f"{path}/{note.code}", json={"body": "переписал"}),
        await client.delete(f"{path}/{note.code}"),
        await client.post(path, json={"title": "Ещё"}),
        await client.put(f"{path}/order", json={"codes": [note.code]}),
    ):
        assert (response.status_code, response.json()["code"]) == (409, "tasks.task.deleted")

    stored = await notes_crud.note_get(note.code)
    assert (stored.body, stored.deleted_at) == ("текст", None)
    assert await _order(task.code) == [note.code]


async def test_delete_takes_the_note_out_of_the_task_softly(client, task):
    kept = await note_crud.task_note_add(task_code=task.code, title="Остаётся")
    gone = await note_crud.task_note_add(task_code=task.code, title="Уходит")

    response = await client.delete(f"{TASKS}/{task.code}/notes/NOTE@{gone.code}")

    assert response.status_code == 204
    assert await _order(task.code) == [kept.code]
    assert (await notes_crud.note_get(gone.code, include_deleted=True)).deleted_at is not None
    assert (await client.get(f"{TASKS}/{task.code}/notes/{gone.code}")).status_code == 404


async def test_the_order_is_saved_as_sent_and_survives_a_reread(client, task):
    a, b, c = [await note_crud.task_note_add(task_code=task.code, title=t) for t in "АБВ"]

    response = await client.put(
        f"{TASKS}/{task.code}/notes/order",
        json={"codes": [f"NOTE@{c.code}", f"NOTE@{a.code}", f"NOTE@{b.code}"]},
    )

    assert response.status_code == 200, response.text
    assert [n["title"] for n in response.json()] == ["В", "А", "Б"]
    assert await _order(task.code) == [c.code, a.code, b.code]


async def test_an_order_naming_a_foreign_note_moves_nothing(client, task):
    a, b = [await note_crud.task_note_add(task_code=task.code, title=t) for t in "АБ"]
    other = await task_crud.task_create(workspace_code=task.workspace_code, title="Другая")
    foreign = await note_crud.task_note_add(task_code=other.code, title="Чужая")

    response = await client.put(
        f"{TASKS}/{task.code}/notes/order", json={"codes": [b.code, foreign.code, a.code]}
    )

    assert response.status_code == 400
    assert f"NOTE@{foreign.code}" in response.json()["error"]
    assert await _order(task.code) == [a.code, b.code]


async def test_a_deleted_note_keeps_its_place_below_a_reorder(client, task):
    a, b, gone = [await note_crud.task_note_add(task_code=task.code, title=t) for t in "АБВ"]
    await notes_crud.note_delete(gone.code)

    await client.put(f"{TASKS}/{task.code}/notes/order", json={"codes": [b.code, a.code]})
    await notes_crud.note_restore(gone.code)

    assert await _order(task.code) == [b.code, a.code, gone.code]
