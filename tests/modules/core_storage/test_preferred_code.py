"""A registration under a code it names, and the lookup by content asked before any write.

The preferred code is the first try only: taken, malformed or beaten by the dedup, the file gets
the code the storage would give it anyway — checked by the rows and bytes left, not by the answer
alone.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest
from sqlalchemy import func, select

from src.core.database import session_scope
from src.modules.core_storage.codes import parse_code
from src.modules.core_storage.dto import Owner
from src.modules.core_storage.models import CoreStorageFile
from src.modules.core_storage.services import files
from src.modules.core_storage.services.files import file_find_content
from src.modules.core_storage.services.registration import (
    file_register_bytes,
    file_register_path,
    file_register_spooled,
    file_spool,
)

pytestmark = pytest.mark.db

TASK = Owner("TASK", "7DB4F6E0DE")
OTHER = Owner("TASK", "BD98065ED2")


async def _rows() -> int:
    async with session_scope() as s:
        return (await s.execute(select(func.count()).select_from(CoreStorageFile))).scalar_one()


async def _chunks(data: bytes):
    yield data


def _source(tmp_path: Path, data: bytes, name: str = "a.txt") -> Path:
    path = tmp_path / name
    path.write_bytes(data)
    return path


async def test_a_free_preferred_code_is_kept(db, tmp_path):
    stored = await file_register_path(
        _source(tmp_path, b"alpha"), store="public", owner=TASK, preferred_code="0123456789"
    )

    assert stored.code == "0123456789"
    assert files.file_path(stored).read_bytes() == b"alpha"


async def test_the_preferred_code_is_taken_in_any_case(db, tmp_path):
    stored = await file_register_path(
        _source(tmp_path, b"alpha"), store="public", owner=TASK, preferred_code="abcdefabcd"
    )

    assert stored.code == "ABCDEFABCD"


async def test_a_spooled_file_keeps_its_preferred_code(db):
    async with file_spool(_chunks(b"spooled")) as spooled:
        stored = await file_register_spooled(
            spooled, store="public", owner=TASK, filename="s.txt", preferred_code="00000000AA"
        )

    assert stored.code == "00000000AA"


async def test_a_taken_preferred_code_falls_back_to_a_random_one(db, tmp_path):
    first = await file_register_path(
        _source(tmp_path, b"first", "first.txt"), store="public", owner=TASK, preferred_code="1111111111"
    )
    second = await file_register_path(
        _source(tmp_path, b"second", "second.txt"), store="public", owner=OTHER, preferred_code="1111111111"
    )

    assert first.code == "1111111111"
    assert second.code != "1111111111"
    assert files.file_path(first).read_bytes() == b"first"
    assert files.file_path(second).read_bytes() == b"second"
    assert await _rows() == 2


@pytest.mark.parametrize("malformed", ["TASK@1111111111", "111111111", "GGGGGGGGGG", ""])
async def test_a_malformed_preferred_code_is_ignored(db, tmp_path, malformed):
    stored = await file_register_path(
        _source(tmp_path, b"alpha"), store="public", owner=TASK, preferred_code=malformed
    )

    # A code of the storage's own making: ten upper-case hex, not anything taken from the input.
    assert parse_code(stored.code) == stored.code
    assert stored.code not in (malformed, malformed.upper(), malformed.split("@")[-1])


async def test_the_same_content_answers_with_its_code_here(db, tmp_path):
    here = await file_register_bytes(b"same bytes", store="public", owner=TASK, filename="a.txt")
    brought = await file_register_path(
        _source(tmp_path, b"same bytes"), store="public", owner=OTHER, preferred_code="2222222222"
    )

    assert brought.code == here.code
    assert await _rows() == 1


async def test_the_content_is_found_before_any_write(db):
    stored = await file_register_bytes(b"content", store="public", owner=TASK, filename="a.txt")
    sha = hashlib.sha256(b"content").hexdigest()

    assert (await file_find_content("public", sha)).code == stored.code
    assert (await file_find_content("public", sha.upper())).code == stored.code
    assert await file_find_content("private", sha) is None
    assert await file_find_content("public", hashlib.sha256(b"other").hexdigest()) is None


async def test_a_soft_deleted_file_is_found_by_its_content(db):
    stored = await file_register_bytes(b"binned", store="public", owner=TASK, filename="a.txt")
    await files.file_delete(stored.code)

    found = await file_find_content("public", hashlib.sha256(b"binned").hexdigest())

    assert found is not None and found.code == stored.code
    assert found.deleted_at is not None
