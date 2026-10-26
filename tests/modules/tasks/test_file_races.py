"""An attach racing a detach or a deletion of the same task: the binding rows and the storage
owners stay pairs.

The interleaving is forced, not hoped for: the attach is stopped right before it writes its row —
after the storage has taken the file — and the other operation is started then. Without the
task's file lock that operation removes the row and releases the owner, and the attach then
writes a row on a released owner. With the lock it waits for the attach to finish.
"""

from __future__ import annotations

import asyncio
import gc

import pytest
from sqlalchemy import select

from src.core.database import session_scope
from src.modules.core_storage.models import CoreStorageFileOwner
from src.modules.core_storage.services.holder_lock import held_locks
from src.modules.core_storage_upload.errors import HolderRefused
from src.modules.core_storage_upload.services import holders as upload_holders
from src.modules.core_storage_upload.services.intake import upload_stream
from src.modules.tasks import files as task_files
from src.modules.tasks.constants import TASK_CODE_PREFIX, TYPE_EXTENDED
from src.modules.tasks.crud import file as file_crud
from src.modules.tasks.crud.stage import stage_create, stage_delete
from src.modules.tasks.crud.task import task_create
from src.modules.tasks.errors import FILE_ALREADY_ATTACHED, TaskRuleError
from src.modules.tasks.file_holders import register_file_holders
from src.modules.tasks.files import FilePlace
from src.modules.tasks.models.file import TasksFile
from tests.modules.tasks.file_support import task_file_attach_bytes

pytestmark = pytest.mark.db

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64
# Long enough for an unserialised detach to finish on an in-memory database; with the lock the
# outcome does not depend on it.
_HEAD_START = 0.5


async def _pairs() -> tuple[set[tuple[str, str]], set[tuple[str, str]]]:
    """``(task, file)`` of every binding row, and of every live ``TASK`` owner."""
    async with session_scope() as s:
        bound = {(r.task_code, r.file_code) for r in (await s.execute(select(TasksFile))).scalars()}
        owners = (
            await s.execute(
                select(CoreStorageFileOwner).where(
                    CoreStorageFileOwner.owner_type == TASK_CODE_PREFIX,
                    CoreStorageFileOwner.deleted_at.is_(None),
                )
            )
        ).scalars()
        held = {(o.owner_id, o.file_code) for o in owners}
    return bound, held


def _pause_before_the_row(monkeypatch) -> tuple[asyncio.Event, asyncio.Event]:
    reached, go = asyncio.Event(), asyncio.Event()
    real_create = file_crud.task_file_create

    async def paused(**kwargs):
        reached.set()
        await go.wait()
        return await real_create(**kwargs)

    monkeypatch.setattr(file_crud, "task_file_create", paused)
    return reached, go


async def _race(attach, other, reached: asyncio.Event, go: asyncio.Event):
    attaching = asyncio.create_task(attach)
    await reached.wait()
    competing = asyncio.create_task(other)
    await asyncio.wait([competing], timeout=_HEAD_START)
    go.set()
    return await asyncio.gather(attaching, competing, return_exceptions=True)


async def test_an_attach_racing_a_detach_of_the_same_file_leaves_pairs(
    workspace, storage, monkeypatch
):
    task = await task_create(workspace_code=workspace.code, title="Гонка", type=TYPE_EXTENDED)
    bound = await task_file_attach_bytes(task.code, PNG, filename="a.png")
    reached, go = _pause_before_the_row(monkeypatch)

    attached, detached = await _race(
        task_file_attach_bytes(task.code, PNG, filename="b.png"),
        task_files.task_file_detach(task.code, bound.file_code),
        reached,
        go,
    )

    bound_rows, live_owners = await _pairs()
    assert bound_rows == live_owners
    # Serialised: the attach found the file bound and refused; the detach then took it out.
    assert isinstance(attached, TaskRuleError) and detached is True
    assert bound_rows == set()


async def test_an_attach_racing_the_deletion_of_the_stage_holding_the_file_leaves_pairs(
    workspace, storage, monkeypatch
):
    task = await task_create(workspace_code=workspace.code, title="Гонка", type=TYPE_EXTENDED)
    stage = await stage_create(task_code=task.code, title="Шаг")
    await task_file_attach_bytes(
        task.code, PNG, filename="a.png", place=FilePlace(stage_code=stage.code)
    )
    reached, go = _pause_before_the_row(monkeypatch)

    await _race(
        task_file_attach_bytes(task.code, PNG, filename="b.png"),
        stage_delete(stage.code),
        reached,
        go,
    )

    bound_rows, live_owners = await _pairs()
    assert bound_rows == live_owners


async def test_the_locks_do_not_outlive_the_operations(workspace, storage):
    tasks = [
        await task_create(workspace_code=workspace.code, title=f"Задача {n}", type=TYPE_EXTENDED)
        for n in range(5)
    ]
    for task in tasks:
        bound = await task_file_attach_bytes(task.code, PNG, filename="a.png")
        await task_files.task_file_detach(task.code, bound.file_code)

    gc.collect()
    assert held_locks() == 0


# How long the other operation may wait on a body still streaming in: a lock held over the stream
# would keep it waiting until the upload ends, which here is never — the gate is still shut.
_NOT_BLOCKED = 2.0


@pytest.fixture
def upload_into_tasks(monkeypatch) -> None:
    """The holders ``TasksModule.configure`` registers, in fresh registries."""
    monkeypatch.setattr(upload_holders, "_holders", {})
    register_file_holders()


async def test_an_upload_still_streaming_does_not_hold_the_task(
    workspace, storage, upload_into_tasks
):
    task = await task_create(workspace_code=workspace.code, title="Медленно", type=TYPE_EXTENDED)
    other = await task_file_attach_bytes(task.code, b"other", filename="o.txt")
    started, gate = asyncio.Event(), asyncio.Event()

    async def slow_body():
        yield b"first part "
        started.set()
        await gate.wait()
        yield b"the rest"

    uploading = asyncio.create_task(
        upload_stream(f"TASK@{task.code}", slow_body(), payload={}, filename="slow.txt")
    )
    await started.wait()

    retitled = await asyncio.wait_for(
        task_files.task_file_retitle(task.code, other.file_code, title="Другой"), _NOT_BLOCKED
    )
    detached = await asyncio.wait_for(
        task_files.task_file_detach(task.code, other.file_code), _NOT_BLOCKED
    )
    gate.set()
    uploaded = await uploading

    assert retitled is not None and detached is True
    assert [f"FILE@{row.file_code}" for row in await file_crud.task_file_list(task.code)] == [
        uploaded["code"]
    ]
    bound_rows, live_owners = await _pairs()
    assert bound_rows == live_owners
    assert [path for path in storage.tmp.rglob("*") if path.is_file()] == []


async def test_an_upload_refused_after_its_body_leaves_no_spare_bytes(
    workspace, storage, upload_into_tasks
):
    task = await task_create(workspace_code=workspace.code, title="Повтор", type=TYPE_EXTENDED)
    await task_file_attach_bytes(task.code, PNG, filename="a.png")

    async def same_bytes():
        yield PNG

    with pytest.raises(HolderRefused) as refused:
        await upload_stream(f"TASK@{task.code}", same_bytes(), payload={}, filename="b.png")

    assert refused.value.code == FILE_ALREADY_ATTACHED

    assert [path for path in storage.tmp.rglob("*") if path.is_file()] == []
    bound_rows, live_owners = await _pairs()
    assert bound_rows == live_owners
