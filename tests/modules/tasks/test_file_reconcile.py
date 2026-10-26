"""The reconciliation of this module's storage owners with its binding rows.

An owner ``("TASK", <task>, "")`` stands for one ``tasks_file`` row. A failure between a deletion's
commit and its release leaves an owner with no row — the file would outlive its task for good; the
reconciliation releases it. The opposite — a row whose file is live and whose owner is not — is
reported, not repaired. Every test reads the storage back.
"""

from __future__ import annotations

import asyncio
from datetime import timedelta

import pytest
from sqlalchemy import delete, update

from src.core.database import write_scope
from src.core.scheduler.registry import get_registry
from src.core.utils.date import utc_now
from src.modules.core_storage.dto import Owner
from src.modules.core_storage.models import CoreStorageFileOwner
from src.modules.core_storage.services.files import file_delete, file_get
from src.modules.core_storage.services.ownership import file_attach, file_owners, file_release
from src.modules.core_storage.services.registration import file_register_bytes
from src.modules.tasks.constants import FILE_OWNER_GRACE, TYPE_EXTENDED
from src.modules.tasks.crud import file as file_crud
from src.modules.tasks.crud.task import task_create, task_delete
from src.modules.tasks.models.file import TasksFile
from src.modules.tasks.reconcile import reconcile_task_owners
from tests.modules.tasks.file_support import task_file_attach_bytes

pytestmark = pytest.mark.db


async def _task(workspace, title: str = "Выпуск"):
    return await task_create(workspace_code=workspace.code, title=title, type=TYPE_EXTENDED)


async def _owners(code: str) -> list[Owner]:
    return [place.owner for place in await file_owners(code)]


async def _drop_row(task_code: str, file_code: str) -> None:
    """A deletion that committed and never reached its release."""
    async with write_scope() as s:
        await s.execute(
            delete(TasksFile).where(TasksFile.task_code == task_code, TasksFile.file_code == file_code)
        )


async def _taken_long_ago(file_code: str, owner: Owner) -> None:
    """Back-date the owner past the grace period — the reconciliation leaves younger ones be."""
    async with write_scope() as s:
        await s.execute(
            update(CoreStorageFileOwner)
            .where(
                CoreStorageFileOwner.file_code == file_code,
                CoreStorageFileOwner.owner_type == owner.type,
                CoreStorageFileOwner.owner_id == owner.id,
            )
            .values(created_at=utc_now() - FILE_OWNER_GRACE - timedelta(minutes=1))
        )


async def test_an_owner_without_a_row_is_released_and_the_bound_ones_stay(workspace, storage):
    task = await _task(workspace)
    orphan = await task_file_attach_bytes(task.code, b"orphan", filename="o.txt")
    bound = await task_file_attach_bytes(task.code, b"bound", filename="b.txt")
    await _drop_row(task.code, orphan.file_code)
    await _taken_long_ago(orphan.file_code, Owner("TASK", task.code))
    await _taken_long_ago(bound.file_code, Owner("TASK", task.code))

    report = await reconcile_task_owners()

    assert report.released == 1
    assert await _owners(orphan.file_code) == []
    assert (await file_get(orphan.file_code, include_deleted=True)).deleted_at is not None
    assert await _owners(bound.file_code) == [Owner("TASK", task.code)]


async def test_an_owner_left_by_a_vanished_task_is_released(workspace, storage):
    """No task row at all — a purge whose release failed."""
    stored = await file_register_bytes(b"left", store="public", owner=Owner("TASK", "ABCDEF0123"))
    await _taken_long_ago(stored.code, Owner("TASK", "ABCDEF0123"))

    assert (await reconcile_task_owners()).released == 1
    assert await _owners(stored.code) == []


async def test_an_owner_younger_than_the_grace_is_kept(workspace, storage):
    """An attach in another process has taken its owner and not yet written its row — the
    process's lock does not reach there, the owner's age does."""
    stored = await file_register_bytes(b"fresh", store="public", owner=Owner("TASK", "ABCDEF0123"))

    assert (await reconcile_task_owners()).released == 0
    assert await _owners(stored.code) == [Owner("TASK", "ABCDEF0123")]


async def test_an_old_owner_taken_again_is_as_young_as_the_new_take(workspace, storage):
    """A released row revived by an attach in flight keeps its first ``created_at`` no longer:
    taking the file again is when the place took it."""
    task = await _task(workspace)
    bound = await task_file_attach_bytes(task.code, b"again", filename="a.txt")
    await _taken_long_ago(bound.file_code, Owner("TASK", task.code))
    await file_release(bound.file_code, Owner("TASK", task.code))
    await _drop_row(task.code, bound.file_code)

    await file_attach(bound.file_code, Owner("TASK", task.code))

    assert (await reconcile_task_owners()).released == 0
    assert await _owners(bound.file_code) == [Owner("TASK", task.code)]


async def test_a_soft_deleted_task_keeps_its_files(workspace, storage):
    task = await _task(workspace)
    bound = await task_file_attach_bytes(task.code, b"kept", filename="k.txt")
    await task_delete(task.code)

    assert (await reconcile_task_owners()).released == 0
    assert await _owners(bound.file_code) == [Owner("TASK", task.code)]


async def test_another_owner_type_is_not_ours_to_release(workspace, storage):
    stored = await file_register_bytes(b"codex", store="public", owner=Owner("CODEX", "AAAAAAAAAA"))

    assert (await reconcile_task_owners()).released == 0
    assert await _owners(stored.code) == [Owner("CODEX", "AAAAAAAAAA")]


async def test_a_row_whose_owner_is_gone_is_reported_not_repaired(workspace, storage):
    task = await _task(workspace)
    bound = await task_file_attach_bytes(task.code, b"unheld", filename="u.txt")
    hidden = await task_file_attach_bytes(task.code, b"hidden", filename="h.txt")
    await file_release(bound.file_code, Owner("TASK", task.code))
    await file_register_bytes(b"unheld", store="public", owner=Owner("CODEX", "AAAAAAAAAA"))
    await file_delete(hidden.file_code)

    report = await reconcile_task_owners()

    # The file the manager deleted keeps its row by design; only the live file is out of step.
    assert report.unheld == [(task.code, bound.file_code)]
    assert await _owners(bound.file_code) == [Owner("CODEX", "AAAAAAAAAA")]
    assert await file_crud.task_file_get(task.code, bound.file_code) is not None


async def test_an_attach_in_flight_is_not_taken_for_an_orphan(workspace, storage, monkeypatch):
    """The attach has taken the owner and not yet written its row; it holds the task's lock, so
    the reconciliation waits and then finds the row."""
    task = await _task(workspace)
    reached, go = asyncio.Event(), asyncio.Event()
    real_create = file_crud.task_file_create

    async def paused(**kwargs):
        reached.set()
        await go.wait()
        return await real_create(**kwargs)

    monkeypatch.setattr(file_crud, "task_file_create", paused)
    attaching = asyncio.create_task(task_file_attach_bytes(task.code, b"in flight"))
    await reached.wait()
    reconciling = asyncio.create_task(reconcile_task_owners())
    await asyncio.wait([reconciling], timeout=0.5)
    go.set()
    bound, report = await asyncio.gather(attaching, reconciling)

    assert report.released == 0
    assert await _owners(bound.file_code) == [Owner("TASK", task.code)]


def test_the_reconciliation_is_scheduled_hourly():
    from fastapi import FastAPI

    from src.core.config import Config
    from src.modules.tasks.module import TasksModule

    TasksModule().configure(FastAPI(), Config())

    task = get_registry().get("tasks", "file_owners")
    assert task is not None and task.schedule == "30 * * * *"
