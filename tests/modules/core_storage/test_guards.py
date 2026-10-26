"""Inputs the storage must refuse before it writes: a malformed owner, a stored file handed over
with ``move``. Each refusal is checked by the state after it — rows and bytes."""

from __future__ import annotations

import pytest
from sqlalchemy import func, select

from src.core.database import session_scope
from src.modules.core_storage.constants import OWNER_ID_MAX, OWNER_KEY_MAX, OWNER_TYPE_MAX
from src.modules.core_storage.dto import Owner
from src.modules.core_storage.errors import SourceInsideStorage
from src.modules.core_storage.models import CoreStorageFile, CoreStorageFileOwner
from src.modules.core_storage.services import files
from src.modules.core_storage.services.registration import file_register_bytes, file_register_path

from .conftest import owners_of

TASK = Owner("task", "7DB4F6E0DE")


@pytest.mark.pure
@pytest.mark.parametrize(
    "fields",
    [
        {"type": "", "id": "1"},
        {"type": "task", "id": ""},
        {"type": "t" * (OWNER_TYPE_MAX + 1), "id": "1"},
        {"type": "task", "id": "i" * (OWNER_ID_MAX + 1)},
        {"type": "task", "id": "1", "key": "k" * (OWNER_KEY_MAX + 1)},
        {"type": "task", "id": "1", "key": None},
        {"type": None, "id": "1"},
        {"type": "task", "id": 7},
    ],
    ids=["empty-type", "empty-id", "long-type", "long-id", "long-key", "none-key", "none-type", "int-id"],
)
def test_a_malformed_owner_is_refused_at_construction(fields):
    with pytest.raises(ValueError):
        Owner(**fields)


@pytest.mark.pure
def test_an_owner_at_every_width_limit_is_accepted():
    owner = Owner("t" * OWNER_TYPE_MAX, "i" * OWNER_ID_MAX, "k" * OWNER_KEY_MAX)
    assert (len(owner.type), len(owner.id), len(owner.key)) == (OWNER_TYPE_MAX, OWNER_ID_MAX, OWNER_KEY_MAX)


@pytest.mark.db
async def test_an_owner_at_every_width_limit_is_stored_whole(db):
    owner = Owner("t" * OWNER_TYPE_MAX, "i" * OWNER_ID_MAX, "k" * OWNER_KEY_MAX)
    stored = await file_register_bytes(b"wide", store="public", owner=owner)
    assert await owners_of(stored.code) == [owner]


async def _counts() -> tuple[int, int]:
    async with session_scope() as s:
        file_rows = (await s.execute(select(func.count()).select_from(CoreStorageFile))).scalar_one()
        owner_rows = (await s.execute(select(func.count()).select_from(CoreStorageFileOwner))).scalar_one()
    return file_rows, owner_rows


@pytest.mark.db
async def test_moving_a_stored_file_is_refused_and_its_bytes_stay(db):
    stored = await file_register_bytes(b"precious", store="public", owner=TASK)
    path = files.file_path(stored)

    with pytest.raises(SourceInsideStorage):
        await file_register_path(path, store="public", owner=Owner("note", "BD98065ED2"), move=True)

    assert path.read_bytes() == b"precious"
    assert await _counts() == (1, 1)


@pytest.mark.db
async def test_moving_any_file_from_inside_the_storage_root_is_refused(db):
    stray = db.root / "stray.bin"
    stray.write_bytes(b"stray")

    with pytest.raises(SourceInsideStorage):
        await file_register_path(stray, store="public", owner=TASK, move=True)

    assert stray.exists()
    assert await _counts() == (0, 0)


@pytest.mark.db
async def test_a_stored_file_registered_again_without_move_is_only_read(db):
    stored = await file_register_bytes(b"precious", store="public", owner=TASK)
    path = files.file_path(stored)

    again = await file_register_path(path, store="public", owner=Owner("note", "BD98065ED2"))

    assert again.code == stored.code
    assert path.read_bytes() == b"precious"
    assert await _counts() == (1, 2)
