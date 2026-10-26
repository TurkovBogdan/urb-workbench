"""Every way a holder of task files goes — and what the storage holds afterwards.

The rule: a final deletion of a task, a task note or a stage releases the task's storage owner of
every file bound there; a soft deletion of a task or a note keeps the files, and a restore brings
them back whole. Each path a person or a CRUD caller has is driven here, and each test reads the
storage back — the owner rows and the file's deletion mark — rather than trusting a 204. The
agent's ``delete`` is driven in ``tests/modules/workbench/test_mcp_delete_files.py``.
"""

from __future__ import annotations

import pytest

from src.modules.core_storage.dto import Owner
from src.modules.core_storage.services.files import file_get
from src.modules.core_storage.services.ownership import file_owners
from src.modules.notes.crud import note as notes_crud
from src.modules.tasks import files as task_files
from src.modules.tasks.constants import TYPE_EXTENDED
from src.modules.tasks.crud import file as file_crud
from src.modules.tasks.crud import note as note_crud
from src.modules.tasks.crud import stage as stage_crud
from src.modules.tasks.crud import task as task_crud
from src.modules.tasks.files import FilePlace
from src.modules.workspace.crud import workspace as workspace_crud
from tests.modules.tasks.file_support import task_file_attach_bytes

pytestmark = pytest.mark.db

TASKS = "/internal/workbench/tasks"


@pytest.fixture
async def workspace_row(client, storage):
    return await workspace_crud.workspace_create(title="Работа")


@pytest.fixture
async def task(workspace_row):
    return await task_crud.task_create(
        workspace_code=workspace_row.code, title="Выпуск", type=TYPE_EXTENDED
    )


async def _attach(task_code: str, name: str, place: FilePlace = FilePlace()) -> str:
    row = await task_file_attach_bytes(
        task_code, name.encode(), filename=f"{name}.txt", place=place
    )
    return row.file_code


async def _owners(code: str) -> list[Owner]:
    return [place.owner for place in await file_owners(code)]


async def _released(code: str) -> bool:
    """No live owner, and the file carries its deletion mark — the cleanup will take it."""
    stored = await file_get(code, include_deleted=True)
    return await _owners(code) == [] and stored.deleted_at is not None


async def _held_by(code: str, task_code: str) -> bool:
    stored = await file_get(code, include_deleted=True)
    return await _owners(code) == [Owner("TASK", task_code)] and stored.deleted_at is None


# ── stage ─────────────────────────────────────────────────────────────────────


async def test_deleting_a_stage_over_http_releases_its_files_only(client, task):
    stage = await stage_crud.stage_create(task_code=task.code, title="Сборка")
    on_stage = await _attach(task.code, "screen", FilePlace(stage_code=stage.code))
    on_task = await _attach(task.code, "spec")

    response = await client.delete(f"/internal/workbench/stages/{stage.code}")

    assert response.status_code == 204
    assert [row.file_code for row in await file_crud.task_file_list(task.code)] == [on_task]
    assert await _released(on_stage)
    assert await _held_by(on_task, task.code)


async def test_deleting_a_stage_through_crud_releases_its_files(client, task):
    stage = await stage_crud.stage_create(task_code=task.code, title="Сборка")
    on_stage = await _attach(task.code, "screen", FilePlace(stage_code=stage.code))

    assert await stage_crud.stage_delete(stage.code) is True

    assert await file_crud.task_file_list(task.code) == []
    assert await _released(on_stage)


async def test_a_stage_file_another_task_holds_stays(client, task, workspace_row):
    other = await task_crud.task_create(workspace_code=workspace_row.code, title="Соседняя")
    stage = await stage_crud.stage_create(task_code=task.code, title="Сборка")
    shared = await _attach(task.code, "screen", FilePlace(stage_code=stage.code))
    await task_files.task_file_attach_existing(other.code, shared)

    await stage_crud.stage_delete(stage.code)

    assert await _held_by(shared, other.code)


# ── task ──────────────────────────────────────────────────────────────────────


async def test_purging_a_task_over_http_releases_the_files_of_its_whole_branch(
    client, task, workspace_row
):
    child = await task_crud.task_create(
        workspace_code=workspace_row.code, title="Подзадача", parent_code=task.code
    )
    note = await note_crud.task_note_add(task_code=task.code, title="Схема")
    stage = await stage_crud.stage_create(task_code=task.code, title="Сборка")
    files = [
        await _attach(task.code, "plain"),
        await _attach(task.code, "on-note", FilePlace(note_code=note.code)),
        await _attach(task.code, "on-stage", FilePlace(stage_code=stage.code)),
        await _attach(child.code, "child"),
    ]
    neighbour = await task_crud.task_create(workspace_code=workspace_row.code, title="Соседняя")
    kept = await _attach(neighbour.code, "kept")

    response = await client.delete(f"{TASKS}/{task.code}/purge")

    assert response.status_code == 204
    for code in files:
        assert await _released(code), code
    assert await file_crud.task_file_list(task.code) == []
    assert await file_crud.task_file_list(child.code) == []
    assert await _held_by(kept, neighbour.code)


async def test_purging_a_task_through_crud_releases_its_files(client, task):
    code = await _attach(task.code, "plain")

    assert await task_crud.task_delete(task.code, hard=True) is True

    assert await _released(code)


async def test_a_soft_deleted_task_keeps_its_files_and_a_restore_brings_them_back(client, task):
    note = await note_crud.task_note_add(task_code=task.code, title="Схема")
    files = [await _attach(task.code, "plain"), await _attach(task.code, "on-note", FilePlace(note_code=note.code))]

    assert (await client.delete(f"{TASKS}/{task.code}")).status_code == 204
    for code in files:
        assert await _held_by(code, task.code)
    listed = (await client.get(f"{TASKS}/{task.code}/files")).json()
    assert [row["code"] for row in listed] == [f"FILE@{code}" for code in files]

    assert (await client.post(f"{TASKS}/{task.code}/restore")).status_code == 200
    assert [row.file_code for row in await file_crud.task_file_list(task.code)] == files


# ── task note ─────────────────────────────────────────────────────────────────


async def test_a_soft_deleted_note_keeps_its_files(client, task):
    note = await note_crud.task_note_add(task_code=task.code, title="Схема")
    code = await _attach(task.code, "on-note", FilePlace(note_code=note.code))

    response = await client.delete(f"{TASKS}/{task.code}/notes/{note.code}")

    assert response.status_code == 204
    assert await _held_by(code, task.code)
    assert [row.note_code for row in await file_crud.task_file_list(task.code)] == [note.code]


async def test_purging_a_note_releases_its_files_and_removes_the_document(client, task):
    note = await note_crud.task_note_add(task_code=task.code, title="Схема")
    on_note = await _attach(task.code, "on-note", FilePlace(note_code=note.code))
    on_task = await _attach(task.code, "plain")

    assert await note_crud.task_note_purge(note.code) is True

    assert await _released(on_note)
    assert await _held_by(on_task, task.code)
    assert await notes_crud.note_get(note.code, include_deleted=True) is None
    assert await note_crud.task_note_task(note.code) is None
    assert await note_crud.task_note_purge(note.code) is False


async def test_a_purged_note_releases_its_files_even_when_the_document_refuses_to_go(
    client, task, monkeypatch
):
    note = await note_crud.task_note_add(task_code=task.code, title="Схема")
    on_note = await _attach(task.code, "on-note", FilePlace(note_code=note.code))

    async def refuse(code, *, hard=False):
        raise RuntimeError("disk full")

    monkeypatch.setattr(notes_crud, "note_delete", refuse)

    with pytest.raises(RuntimeError):
        await note_crud.task_note_purge(note.code)

    assert await file_crud.task_file_list(task.code) == []
    assert await _released(on_note)
