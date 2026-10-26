"""The reconciliation of the codex's storage owners with its binding rows — the same rules as the
tasks' (``tests/modules/tasks/test_file_reconcile.py``), for owners of type ``CODEX``."""

from __future__ import annotations

from datetime import timedelta

import pytest
from sqlalchemy import delete, update

from src.core.database import write_scope
from src.core.scheduler.registry import get_registry
from src.core.utils.date import utc_now
from src.modules.codex.constants import FILE_OWNER_GRACE
from src.modules.codex.crud import codex as codex_crud
from src.modules.codex.crud import file as file_crud
from src.modules.codex.crud import note as note_crud
from src.modules.codex.models import CodexFile
from src.modules.codex.reconcile import reconcile_note_owners
from src.modules.core_storage.dto import Owner
from src.modules.core_storage.models import CoreStorageFileOwner
from src.modules.core_storage.services.files import file_get
from src.modules.core_storage.services.ownership import file_owners, file_release
from src.modules.core_storage.services.registration import file_register_bytes
from tests.modules.codex.file_support import codex_file_attach_bytes

pytestmark = pytest.mark.db


@pytest.fixture
async def codex(db, storage):
    return await codex_crud.codex_create(segment="python", title="Python")


@pytest.fixture
async def note(codex):
    return await note_crud.note_create(parent_code=codex.code, segment="test", title="Тесты")


async def _owners(code: str) -> list[Owner]:
    return [place.owner for place in await file_owners(code)]


async def test_an_owner_without_a_row_is_released_and_the_bound_ones_stay(note):
    orphan = await codex_file_attach_bytes(note.code, b"orphan", filename="o.txt")
    bound = await codex_file_attach_bytes(note.code, b"bound", filename="b.txt")
    async with write_scope() as s:
        await s.execute(
            delete(CodexFile).where(
                CodexFile.note_code == note.code, CodexFile.file_code == orphan.file_code
            )
        )
        await s.execute(
            update(CoreStorageFileOwner).values(
                created_at=utc_now() - FILE_OWNER_GRACE - timedelta(minutes=1)
            )
        )

    report = await reconcile_note_owners()

    assert report.released == 1
    assert await _owners(orphan.file_code) == []
    assert (await file_get(orphan.file_code, include_deleted=True)).deleted_at is not None
    assert await _owners(bound.file_code) == [Owner("CODEX", note.code)]


async def test_an_owner_younger_than_the_grace_is_kept(note):
    """An attach in another process has taken its owner and not yet written its row."""
    stored = await file_register_bytes(b"fresh", store="public", owner=Owner("CODEX", note.code))

    assert (await reconcile_note_owners()).released == 0
    assert await _owners(stored.code) == [Owner("CODEX", note.code)]


async def test_soft_deleted_notes_and_codexes_keep_their_files(codex, note):
    other = await note_crud.note_create(parent_code=codex.code, segment="style", title="Стиль")
    on_note = await codex_file_attach_bytes(note.code, b"note", filename="n.txt")
    on_other = await codex_file_attach_bytes(other.code, b"other", filename="o.txt")
    await note_crud.note_delete(note.code)
    await codex_crud.codex_delete(codex.code)

    assert (await reconcile_note_owners()).released == 0
    assert await _owners(on_note.file_code) == [Owner("CODEX", note.code)]
    assert await _owners(on_other.file_code) == [Owner("CODEX", other.code)]


async def test_a_task_owner_is_not_ours_to_release(note):
    stored = await file_register_bytes(b"task", store="public", owner=Owner("TASK", "AAAAAAAAAA"))

    assert (await reconcile_note_owners()).released == 0
    assert await _owners(stored.code) == [Owner("TASK", "AAAAAAAAAA")]


async def test_a_row_whose_owner_is_gone_is_reported_not_repaired(note):
    bound = await codex_file_attach_bytes(note.code, b"unheld", filename="u.txt")
    await file_release(bound.file_code, Owner("CODEX", note.code))
    await file_register_bytes(b"unheld", store="public", owner=Owner("TASK", "AAAAAAAAAA"))

    report = await reconcile_note_owners()

    assert report.unheld == [(note.code, bound.file_code)]
    assert await file_crud.codex_file_get(note.code, bound.file_code) is not None


def test_the_reconciliation_is_scheduled_hourly():
    from fastapi import FastAPI

    from src.core.config import Config
    from src.modules.codex.module import CodexModule

    CodexModule().configure(FastAPI(), Config())

    task = get_registry().get("codex", "file_owners")
    assert task is not None and task.schedule == "30 * * * *"
