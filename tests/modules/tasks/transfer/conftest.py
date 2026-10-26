"""Task transfer fixtures: a base with every table, a task «with everything», and a second
installation to import into.

``rich_task`` is the full stuffing: an extended root in a group with a subtask (and a deleted one
that must not travel), stages, journal entries in the task and in a stage, notes (and a deleted
one), files in the task, in a note and in a stage, a file both the root and the subtask hold, and
texts that refer to all of it — plus a reference to a task outside the archive.

``other_installation`` swaps the base and the storage for empty ones: the same process, another
installation — what a real transfer is.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from src.core.api import register_exception_handlers
from src.core.config import Config
from src.core.database import close_database, init_database
from src.modules.core_storage import layout as storage_layout
from src.modules.core_storage import settings as storage_settings
from src.modules.core_storage.layout import StorageLayout
from src.modules.core_transfer import uploads
from src.modules.tasks.api import router
from src.modules.tasks.crud import group as group_crud
from src.modules.tasks.crud import journal as journal_crud
from src.modules.tasks.crud import note as note_crud
from src.modules.tasks.crud import stage as stage_crud
from src.modules.tasks.crud import task as task_crud
from src.modules.tasks.files import FilePlace
from src.modules.workspace.crud.workspace import workspace_create

from ..file_support import task_file_attach_bytes

PNG = bytes.fromhex("89504e470d0a1a0a0000000d49484452") + b"\x00" * 64


async def _schema(config: Config) -> None:
    engine = await init_database(config)
    from src.core.database.runtime import Base
    import src.core.models  # noqa: F401 — the module state store (installation id)
    import src.modules.codex.models  # noqa: F401 — a codex record may hold the same bytes as a task
    import src.modules.tasks.models  # noqa: F401
    import src.modules.workspace.models  # noqa: F401

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


def _layout(root: Path, monkeypatch: pytest.MonkeyPatch) -> StorageLayout:
    layout = StorageLayout(root / "storage", root / "tmp", ("public", "private"))
    layout.ensure_dirs()
    monkeypatch.setattr(storage_layout, "_layout", layout)
    monkeypatch.setattr(storage_settings, "_current", None)
    return layout


@pytest.fixture(autouse=True)
def transfer_folder(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    root = tmp_path / "transfer"
    monkeypatch.setattr(uploads, "transfer_root", lambda: root)
    return root


@pytest.fixture
def storage(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> StorageLayout:
    return _layout(tmp_path / "first", monkeypatch)


@pytest.fixture
async def db(config: Config, storage: StorageLayout):
    await _schema(config)
    try:
        yield storage
    finally:
        await close_database()


@pytest.fixture
async def client(db):
    app = FastAPI()
    register_exception_handlers(app)
    app.include_router(router, prefix="/internal/workbench")
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


@pytest.fixture
def other_installation(config: Config, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Call to move to an empty base and an empty storage; returns the new storage layout."""

    async def move() -> StorageLayout:
        await close_database()
        layout = _layout(tmp_path / "second", monkeypatch)
        await _schema(config)
        return layout

    return move


@dataclass
class RichTask:
    workspace: str
    group: str
    root: str
    child: str
    deleted_child: str
    outside: str
    stages: list[str]
    child_stage: str
    entries: list[str]
    notes: list[str]
    deleted_note: str
    child_note: str
    task_file: str
    note_file: str
    stage_file: str
    shared_file: str


async def make_rich_task(workspace_title: str = "Работа") -> RichTask:
    workspace = (await workspace_create(title=workspace_title)).code
    group = (await group_crud.group_create(workspace_code=workspace, title="Модуль")).code
    outside = (await task_crud.task_create(workspace_code=workspace, title="Чужая задача")).code
    root = (await task_crud.task_create(
        workspace_code=workspace, group_code=group, title="Перенос задачи", type="extended",
        description="Цель", status="in_progress", priority="high", created_by="agent",
    )).code
    child = (await task_crud.task_create(
        workspace_code=workspace, parent_code=root, title="Подзадача", type="extended",
    )).code
    deleted_child = (await task_crud.task_create(workspace_code=workspace, parent_code=root, title="Удалённая")).code
    await task_crud.task_delete(deleted_child)

    first = await stage_crud.stage_create(task_code=root, title="Первый этап", body="Делаем")
    second = await stage_crud.stage_create(task_code=root, title="Второй этап")
    await stage_crud.stage_update(first.code, evidence="pytest → ok")
    await stage_crud.stage_update_status(first.code, "done")
    child_stage = await stage_crud.stage_create(task_code=child, title="Этап подзадачи")

    decision = await journal_crud.journal_create(task_code=root, type="decision", title="Решение", body="Почему")
    fact = await journal_crud.journal_create(task_code=root, type="fact", title="Факт", stage_code=first.code,
                                             resolution="записано")
    await journal_crud.journal_resolve(decision.code, "принято")
    child_entry = await journal_crud.journal_create(task_code=child, type="finding", title="Находка")

    schema = await note_crud.task_note_add(task_code=root, title="Схема", description="когда", body="Тело заметки")
    second_note = await note_crud.task_note_add(task_code=root, title="Вторая", body="")
    deleted_note = await note_crud.task_note_add(task_code=root, title="Удалённая заметка", body="x")
    from src.modules.notes.crud.note import note_delete

    await note_delete(deleted_note.code)
    child_note = await note_crud.task_note_add(task_code=child, title="Заметка подзадачи", body="тело")

    task_file = await task_file_attach_bytes(root, PNG, filename="shot.png", title="Скриншот")
    note_file = await task_file_attach_bytes(root, b"note bytes", filename="a.txt",
                                             place=FilePlace(note_code=schema.code), title="К заметке")
    stage_file = await task_file_attach_bytes(root, b"stage bytes", filename="b.txt",
                                              place=FilePlace(stage_code=first.code))
    shared = await task_file_attach_bytes(root, b"shared bytes", filename="c.txt")
    await task_file_attach_bytes(child, b"shared bytes", filename="c.txt", title="Общий")

    refs = (
        f"Смотри NOTE@{schema.code}, ![картинка](IMAGE@{task_file.file_code}), FILE@{note_file.file_code}, "
        f"STAGE@{first.code}, JOURNAL@{decision.code}, TASK@{child} и чужую TASK@{outside}"
    )
    await task_crud.task_update(root, context=refs, plan=f"План: NOTE@{second_note.code}")
    from src.modules.notes.crud.note import note_update

    await note_update(schema.code, body=f"Тело заметки со ссылкой на STAGE@{second.code} и TASK@{root}")

    return RichTask(
        workspace=workspace, group=group, root=root, child=child, deleted_child=deleted_child, outside=outside,
        stages=[first.code, second.code], child_stage=child_stage.code,
        entries=[decision.code, fact.code, child_entry.code], notes=[schema.code, second_note.code],
        deleted_note=deleted_note.code, child_note=child_note.code, task_file=task_file.file_code,
        note_file=note_file.file_code, stage_file=stage_file.file_code, shared_file=shared.file_code,
    )


@pytest.fixture
async def rich(db) -> RichTask:
    return await make_rich_task()
