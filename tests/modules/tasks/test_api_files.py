"""HTTP API of a task's files: the list the page shows, re-titling, the order, detaching.

The files here are attached through the service, as the uploads do; the person's upload is
``test_upload_holder.py``. Every refusal is checked by the state after it.
"""

from __future__ import annotations

import pytest

from src.modules.core_storage.services.files import file_delete
from src.modules.core_storage.services.ownership import file_owners
from src.modules.tasks.constants import FILE_DESCRIPTION_MAX, FILE_TITLE_MAX, TYPE_EXTENDED
from src.modules.tasks.crud import file as file_crud
from src.modules.tasks.crud import note as note_crud
from src.modules.tasks.crud import stage as stage_crud
from src.modules.tasks.crud import task as task_crud
from src.modules.tasks.files import FilePlace
from src.modules.workspace.crud import workspace as workspace_crud
from tests.modules.tasks.file_support import task_file_attach_bytes

pytestmark = pytest.mark.db

TASKS = "/internal/workbench/tasks"
PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64


@pytest.fixture
async def task(client, storage):
    workspace = await workspace_crud.workspace_create(title="Работа")
    return await task_crud.task_create(
        workspace_code=workspace.code, title="Выпуск", type=TYPE_EXTENDED
    )


async def _order(task_code: str) -> list[str]:
    return [row.file_code for row in await file_crud.task_file_list(task_code)]


async def test_the_list_carries_the_binding_and_what_the_storage_knows(client, task):
    note = await note_crud.task_note_add(task_code=task.code, title="Схема")
    stage = await stage_crud.stage_create(task_code=task.code, title="Сборка")
    image = await task_file_attach_bytes(
        task.code, PNG, filename="Экран.PNG", title="Главный экран", description="После входа"
    )
    on_note = await task_file_attach_bytes(
        task.code, b"a", filename="a.txt", place=FilePlace(note_code=note.code)
    )
    on_stage = await task_file_attach_bytes(
        task.code, b"b", filename="b.log", place=FilePlace(stage_code=stage.code)
    )

    response = await client.get(f"{TASKS}/task@{task.code.lower()}/files")

    assert response.status_code == 200, response.text
    rows = response.json()
    assert [row["code"] for row in rows] == [
        f"FILE@{image.file_code}",
        f"FILE@{on_note.file_code}",
        f"FILE@{on_stage.file_code}",
    ]
    first = rows[0]
    assert {key: first[key] for key in (
        "task_code", "note_code", "stage_code", "title", "description",
        "original_filename", "original_extension", "mime", "type", "size", "sort",
    )} == {
        "task_code": f"TASK@{task.code}",
        "note_code": None,
        "stage_code": None,
        "title": "Главный экран",
        "description": "После входа",
        "original_filename": "Экран",
        "original_extension": ".PNG",
        "mime": "image/png",
        "type": "image",
        "size": len(PNG),
        "sort": image.sort,
    }
    assert "T" not in first["created_at"]
    assert (rows[1]["note_code"], rows[2]["stage_code"]) == (f"NOTE@{note.code}", f"STAGE@{stage.code}")


async def test_an_unknown_task_is_404(client, task):
    response = await client.get(f"{TASKS}/0000000000/files")

    assert response.status_code == 404
    assert response.json()["code"] == "tasks.task.not_found"


async def test_patch_changes_only_what_was_sent(client, task):
    bound = await task_file_attach_bytes(task.code, PNG, filename="x.png", description="Было")

    response = await client.patch(
        f"{TASKS}/{task.code}/files/file@{bound.file_code.lower()}", json={"title": "Экран"}
    )

    assert response.status_code == 200, response.text
    assert (response.json()["title"], response.json()["description"]) == ("Экран", "Было")
    row = await file_crud.task_file_get(task.code, bound.file_code)
    assert (row.title, row.description) == ("Экран", "Было")


@pytest.mark.parametrize(
    "body",
    [
        {"title": "т" * (FILE_TITLE_MAX + 1)},
        {"description": "о" * (FILE_DESCRIPTION_MAX + 1)},
        {"name": "x"},
    ],
)
async def test_patch_over_the_limit_or_with_an_extra_field_is_422_and_writes_nothing(client, task, body):
    bound = await task_file_attach_bytes(task.code, PNG, filename="x.png", title="Было")

    response = await client.patch(f"{TASKS}/{task.code}/files/{bound.file_code}", json=body)

    assert response.status_code == 422
    assert (await file_crud.task_file_get(task.code, bound.file_code)).title == "Было"


async def test_patch_of_a_file_not_in_the_task_is_404(client, task):
    response = await client.patch(f"{TASKS}/{task.code}/files/0000000000", json={"title": "x"})

    assert response.status_code == 404
    assert response.json()["code"] == "tasks.file.not_found"


async def test_patch_of_a_file_the_file_manager_deleted_is_404_and_writes_nothing(client, task):
    """The binding stays when the file manager deletes the file, and the list hides it; an edit
    of it would land where nobody sees it."""
    bound = await task_file_attach_bytes(task.code, PNG, filename="x.png", title="Было")
    await file_delete(bound.file_code)

    response = await client.patch(
        f"{TASKS}/{task.code}/files/{bound.file_code}", json={"title": "Стало"}
    )

    assert response.status_code == 404
    assert response.json()["code"] == "tasks.file.not_found"
    assert (await file_crud.task_file_get(task.code, bound.file_code)).title == "Было"


async def test_a_foreign_code_type_is_400(client, task):
    response = await client.patch(f"{TASKS}/{task.code}/files/NOTE@0000000000", json={"title": "x"})

    assert response.status_code == 400


async def test_put_order_renumbers_and_answers_with_the_list(client, task):
    codes = [
        (await task_file_attach_bytes(task.code, bytes([n]), filename=f"{n}.txt")).file_code
        for n in range(3)
    ]

    response = await client.put(
        f"{TASKS}/{task.code}/files/order", json={"codes": [f"FILE@{codes[2]}", codes[1], codes[0]]}
    )

    assert response.status_code == 200, response.text
    assert [row["code"] for row in response.json()] == [f"FILE@{c}" for c in reversed(codes)]
    assert await _order(task.code) == list(reversed(codes))


async def test_put_order_with_a_foreign_file_is_400_and_moves_nothing(client, task):
    codes = [
        (await task_file_attach_bytes(task.code, bytes([n]), filename=f"{n}.txt")).file_code
        for n in range(2)
    ]

    response = await client.put(
        f"{TASKS}/{task.code}/files/order", json={"codes": [codes[1], "0000000000"]}
    )

    assert response.status_code == 400
    assert response.json()["code"] == "tasks.file.not_found"
    assert await _order(task.code) == codes


async def test_delete_detaches_and_releases_the_owner(client, task):
    bound = await task_file_attach_bytes(task.code, PNG, filename="x.png")

    response = await client.delete(f"{TASKS}/{task.code}/files/{bound.file_code}")
    again = await client.delete(f"{TASKS}/{task.code}/files/{bound.file_code}")

    assert response.status_code == 204
    assert again.status_code == 404 and again.json()["code"] == "tasks.file.not_found"
    assert await _order(task.code) == []
    assert await file_owners(bound.file_code) == []


async def test_a_deleted_task_s_files_are_read_but_not_changed(client, task):
    bound = await task_file_attach_bytes(task.code, PNG, filename="x.png", title="Было")
    await task_crud.task_delete(task.code)

    listed = await client.get(f"{TASKS}/{task.code}/files")
    patched = await client.patch(f"{TASKS}/{task.code}/files/{bound.file_code}", json={"title": "x"})
    ordered = await client.put(f"{TASKS}/{task.code}/files/order", json={"codes": [bound.file_code]})
    detached = await client.delete(f"{TASKS}/{task.code}/files/{bound.file_code}")

    assert listed.status_code == 200 and len(listed.json()) == 1
    for response in (patched, ordered, detached):
        assert response.status_code == 409
        assert response.json()["code"] == "tasks.task.deleted"
    assert (await file_crud.task_file_get(task.code, bound.file_code)).title == "Было"
    assert len(await file_owners(bound.file_code)) == 1
