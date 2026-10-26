"""workbench MCP: the agent's ``delete`` and the files the deleted entity held.

``delete`` removes a stage outright, and with it the files attached there: their bindings go and
the task's storage owner of each is released. A task and a task note go to the bin, and keep their
files for a restore; a codex note likewise — a codex has no final deletion. Each test reads the
storage back after the call, not the tool's answer.
"""

from __future__ import annotations

import pytest

from src.modules.codex.crud import codex as codex_crud
from src.modules.codex.crud import mount as mount_crud
from src.modules.codex.crud import note as codex_note_crud
from src.modules.core_storage.dto import Owner
from src.modules.core_storage.services.files import file_get
from src.modules.core_storage.services.ownership import file_owners
from src.modules.tasks.constants import TYPE_EXTENDED
from src.modules.tasks.crud import file as file_crud
from src.modules.tasks.crud import note as note_crud
from src.modules.tasks.crud import stage as stage_crud
from src.modules.tasks.crud import task as task_crud
from src.modules.tasks.files import FilePlace
from tests.modules.codex.file_support import codex_file_attach_bytes
from tests.modules.tasks.file_support import task_file_attach_bytes

pytestmark = pytest.mark.db


@pytest.fixture
async def task(call, workspace, storage):
    await call("workspace_use", workspace_code=workspace.code)
    return await task_crud.task_create(
        workspace_code=workspace.code, title="Выпуск", type=TYPE_EXTENDED
    )


async def _owners(code: str) -> list[Owner]:
    return [place.owner for place in await file_owners(code)]


async def test_deleting_a_stage_releases_the_files_attached_there(call, task):
    stage = await stage_crud.stage_create(task_code=task.code, title="Сборка")
    on_stage = await task_file_attach_bytes(
        task.code, b"screen", filename="screen.png", place=FilePlace(stage_code=stage.code)
    )
    on_task = await task_file_attach_bytes(task.code, b"spec", filename="spec.md")

    assert (await call("delete", code=f"STAGE@{stage.code}"))["result"] is True

    assert [row.file_code for row in await file_crud.task_file_list(task.code)] == [on_task.file_code]
    assert await _owners(on_stage.file_code) == []
    assert (await file_get(on_stage.file_code, include_deleted=True)).deleted_at is not None
    assert await _owners(on_task.file_code) == [Owner("TASK", task.code)]


async def test_deleting_a_task_keeps_its_files_in_the_bin(call, task):
    bound = await task_file_attach_bytes(task.code, b"spec", filename="spec.md")

    assert (await call("delete", code=f"TASK@{task.code}"))["result"] is True

    assert [row.file_code for row in await file_crud.task_file_list(task.code)] == [bound.file_code]
    assert await _owners(bound.file_code) == [Owner("TASK", task.code)]
    assert (await file_get(bound.file_code)).deleted_at is None


async def test_deleting_a_task_note_keeps_its_files(call, task):
    note = await note_crud.task_note_add(task_code=task.code, title="Схема")
    bound = await task_file_attach_bytes(
        task.code, b"schema", filename="schema.svg", place=FilePlace(note_code=note.code)
    )

    assert (await call("delete", code=f"NOTE@{note.code}"))["result"] is True

    assert await _owners(bound.file_code) == [Owner("TASK", task.code)]
    assert (await file_crud.task_file_get(task.code, bound.file_code)).note_code == note.code


async def test_deleting_a_codex_note_keeps_its_files(call, task, workspace):
    codex = await codex_crud.codex_create(segment="python", title="Python")
    await mount_crud.mount_add(codex.code, workspace.code, agent_can_edit=True)
    note = await codex_note_crud.note_create(parent_code=codex.code, segment="test", title="Тесты")
    bound = await codex_file_attach_bytes(note.code, b"diagram", filename="flow.svg")

    assert (await call("delete", code=f"CODEX@{note.code}"))["result"] is True

    assert await _owners(bound.file_code) == [Owner("CODEX", note.code)]
    assert (await file_get(bound.file_code)).deleted_at is None
