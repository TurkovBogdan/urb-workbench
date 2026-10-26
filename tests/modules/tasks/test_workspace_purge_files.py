"""The final deletion of a workspace lets go of its tasks' files in the storage.

The FK cascade takes the tasks and their ``tasks_file`` rows away without a word to this module;
the hook this module registers in ``workspace`` collects the tasks before the cascade and releases
their storage owners after the commit. What a test asserts is the storage afterwards — who still
holds each file, and whether it carries the deletion mark.
"""

from __future__ import annotations

import pytest

from src.modules.core_storage.dto import Owner
from src.modules.core_storage.services.files import file_get
from src.modules.core_storage.services.ownership import file_attach, file_owners
from src.modules.tasks.constants import TYPE_EXTENDED
from src.modules.tasks.crud import file as file_crud
from src.modules.tasks.crud.note import task_note_add
from src.modules.tasks.crud.stage import stage_create
from src.modules.tasks.crud.task import task_create, task_delete
from src.modules.tasks.files import FilePlace
from src.modules.tasks.workspace_purge import WORKSPACE_PURGE_HOOK
from src.modules.workspace.crud import workspace as workspace_crud
from src.modules.workspace.purge import register_purge_hook, reset_purge_hooks
from tests.modules.tasks.file_support import task_file_attach_bytes

pytestmark = pytest.mark.db


@pytest.fixture(autouse=True)
def purge_hook():
    reset_purge_hooks()
    register_purge_hook(WORKSPACE_PURGE_HOOK)
    yield
    reset_purge_hooks()


async def _owners(code: str) -> list[Owner]:
    return [place.owner for place in await file_owners(code)]


async def _marked(code: str) -> bool:
    return (await file_get(code, include_deleted=True)).deleted_at is not None


async def _workspace_with_files(title: str):
    """A workspace whose files sit on a task, on its note, on its stage, on a subtask and on a
    soft-deleted task — every place the cascade reaches."""
    workspace = await workspace_crud.workspace_create(title=title)
    task = await task_create(workspace_code=workspace.code, title="Выпуск", type=TYPE_EXTENDED)
    note = await task_note_add(task_code=task.code, title="Схема")
    stage = await stage_create(task_code=task.code, title="Сборка")
    child = await task_create(
        workspace_code=workspace.code, title="Часть", type=TYPE_EXTENDED, parent_code=task.code
    )
    gone = await task_create(workspace_code=workspace.code, title="Удалена", type=TYPE_EXTENDED)
    files = [
        await task_file_attach_bytes(task.code, f"{title}-task".encode()),
        await task_file_attach_bytes(
            task.code, f"{title}-note".encode(), place=FilePlace(note_code=note.code)
        ),
        await task_file_attach_bytes(
            task.code, f"{title}-stage".encode(), place=FilePlace(stage_code=stage.code)
        ),
        await task_file_attach_bytes(child.code, f"{title}-child".encode()),
        await task_file_attach_bytes(gone.code, f"{title}-gone".encode()),
    ]
    await task_delete(gone.code)
    return workspace, task, [row.file_code for row in files]


async def test_a_purge_releases_every_file_of_the_workspace_s_tasks(db, storage):
    workspace, _, codes = await _workspace_with_files("Под снос")

    assert await workspace_crud.workspace_delete(workspace.code, hard=True) is True

    for code in codes:
        assert await _owners(code) == []
        assert await _marked(code)


async def test_another_workspace_and_another_holder_keep_their_files(db, storage):
    doomed, doomed_task, doomed_codes = await _workspace_with_files("Под снос")
    kept, kept_task, kept_codes = await _workspace_with_files("Остаётся")
    shared = doomed_codes[0]
    await file_attach(shared, Owner("CODEX", "AAAAAAAAAA"))

    await workspace_crud.workspace_delete(doomed.code, hard=True)

    for code in kept_codes:
        assert len(await _owners(code)) == 1 and not await _marked(code)
    assert await _owners(shared) == [Owner("CODEX", "AAAAAAAAAA")]
    assert not await _marked(shared)
    assert len(await file_crud.task_file_list(kept_task.code)) == 3


async def test_a_soft_delete_of_a_workspace_keeps_the_files_held(db, storage):
    workspace, _, codes = await _workspace_with_files("Корзина")

    await workspace_crud.workspace_delete(workspace.code)

    for code in codes:
        assert len(await _owners(code)) == 1 and not await _marked(code)


def test_building_the_app_registers_the_hook(monkeypatch: pytest.MonkeyPatch):
    from src.apps.app.modules import build_modules
    from src.core.app_factory import create_app
    from src.core.config import Config
    from src.modules.core_storage import layout
    from src.modules.workspace.purge import registered_purge_hooks

    # The build sets the storage layout to the profile's folders; the patch puts it back after.
    monkeypatch.setattr(layout, "_layout", None)
    reset_purge_hooks()
    create_app(modules=build_modules(), config=Config())

    assert [hook.key for hook in registered_purge_hooks()] == ["tasks"]


async def test_the_http_purge_releases_the_files(db, storage):
    from fastapi import FastAPI
    from httpx import ASGITransport, AsyncClient

    from src.core.api import register_exception_handlers
    from src.modules.workspace.api import router

    app = FastAPI()
    register_exception_handlers(app)
    app.include_router(router, prefix="/internal/workspace")
    workspace, _, codes = await _workspace_with_files("Через HTTP")

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.delete(f"/internal/workspace/{workspace.code}/purge")

    assert response.status_code == 204
    for code in codes:
        assert await _owners(code) == []
