"""Choices checked against what each conflict offers, files judged and taken by «code + sha256»,
uploads kept under their own id."""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from src.modules.core_storage.dto import Owner
from src.modules.core_storage.services.files import file_delete, file_get
from src.modules.core_storage.services.ownership import file_owners
from src.modules.core_storage.services.registration import file_register_bytes
from src.modules.core_transfer import errors
from src.modules.core_transfer.conflicts import Side, both_ways, only_replace, plan_token, resolve_choices
from src.modules.core_transfer.container import ArchiveReader, ArchiveWriter
from src.modules.core_transfer.errors import TransferError
from src.modules.core_transfer.files import (
    FILE_CONFLICT,
    FILE_CREATE,
    FILE_RECODE,
    FILE_REUSE,
    ArchivedFile,
    judge_files,
    release_taken,
    take_file,
)
from src.modules.core_transfer.install import install_id
from src.modules.core_transfer.manifest import ManifestRoot, ManifestSource
from src.modules.core_transfer.uploads import UploadArea

from .conftest import FORMAT

TASK = Owner("TASK", "1111111111")
HERE = Owner("TASK", "2222222222")
SIDE = Side(updated_at="2026-10-26 07:00:00")


def _task_conflict():
    return both_ways("TASK@AAAAAAAAAA", "task", "T", {}, here=SIDE, archive=SIDE)


def _note_conflict():
    return both_ways("NOTE@BBBBBBBBBB", "note", "N", {}, here=SIDE, archive=SIDE,
                     requires=("TASK@AAAAAAAAAA", "update"))


@pytest.mark.pure
def test_every_conflict_needs_a_choice():
    with pytest.raises(TransferError) as caught:
        resolve_choices([_task_conflict()], {})

    assert caught.value.code == errors.DECISION_INVALID
    assert caught.value.params == {"id": "TASK@AAAAAAAAAA"}


@pytest.mark.pure
def test_a_single_option_is_chosen_by_itself():
    conflict = only_replace("NOTE@CCCCCCCCCC", "note", "N", {}, here=SIDE, archive=SIDE, reason="foreign_task")

    assert resolve_choices([conflict], {}) == {"NOTE@CCCCCCCCCC": "replace"}
    with pytest.raises(TransferError):
        resolve_choices([conflict], {"NOTE@CCCCCCCCCC": "update"})


@pytest.mark.pure
def test_an_update_needs_what_it_requires():
    conflicts = [_task_conflict(), _note_conflict()]

    with pytest.raises(TransferError):
        resolve_choices(conflicts, {"TASK@AAAAAAAAAA": "replace", "NOTE@BBBBBBBBBB": "update"})

    assert resolve_choices(conflicts, {"TASK@AAAAAAAAAA": "update", "NOTE@BBBBBBBBBB": "update"}) == {
        "TASK@AAAAAAAAAA": "update", "NOTE@BBBBBBBBBB": "update",
    }
    assert resolve_choices(conflicts, {"TASK@AAAAAAAAAA": "replace", "NOTE@BBBBBBBBBB": "replace"})


@pytest.mark.pure
def test_the_token_follows_the_options_not_the_dates():
    one = plan_token([_task_conflict()])
    later = both_ways("TASK@AAAAAAAAAA", "task", "T", {}, here=Side("2027-01-01 00:00:00"), archive=SIDE)
    narrowed = only_replace("TASK@AAAAAAAAAA", "task", "T", {}, here=SIDE, archive=SIDE, reason="x")

    assert plan_token([later]) == one
    assert plan_token([narrowed]) != one
    assert plan_token([_task_conflict()], ["recode:STAGE@1"]) != one


@pytest.mark.pure
def test_the_dates_of_both_sides_go_out():
    conflict = both_ways("FILE@AAAAAAAAAA", "file", "F", {}, here=Side("a", "b", 1), archive=Side("c", "d", 2))

    assert conflict.as_dict()["dates"] == {
        "local": {"updated_at": "a", "created_at": "b", "size": 1},
        "archive": {"updated_at": "c", "created_at": "d", "size": 2},
    }


def _archive_with(path: Path, files: dict[str, bytes]) -> Path:
    with ArchiveWriter(path, FORMAT) as archive:
        for code, data in files.items():
            source = path.parent / f"{code}.bin"
            source.write_bytes(data)
            archive.add_file(f"files/{code}.png", source)
        archive.finish(
            archive_id="01J00000000000000000000000",
            source=ManifestSource(),
            root=ManifestRoot(code="AAAAAAAAAA"),
            counts={},
            dangling_refs=[],
        )
    return path


def _archived(code: str, data: bytes) -> ArchivedFile:
    return ArchivedFile(code=code, sha256=hashlib.sha256(data).hexdigest(), size=len(data),
                        entry=f"files/{code}.png", filename="pic.png")


@pytest.mark.db
async def test_files_are_judged_by_code_and_content(db):
    reused = await file_register_bytes(b"same", store="public", owner=HERE, filename="a.txt")
    other = await file_register_bytes(b"here", store="public", owner=HERE, filename="b.txt")

    verdicts = await judge_files(
        [
            _archived(reused.code, b"same"),
            _archived("CCCCCCCCCC", b"same"),
            _archived(other.code, b"different"),
            _archived("DDDDDDDDDD", b"new"),
        ],
        store="public",
    )

    assert verdicts[reused.code].outcome == FILE_REUSE
    assert verdicts["CCCCCCCCCC"].outcome == FILE_RECODE and verdicts["CCCCCCCCCC"].code_here == reused.code
    assert verdicts[other.code].outcome == FILE_CONFLICT and verdicts[other.code].code_here is None
    assert verdicts["DDDDDDDDDD"].outcome == FILE_CREATE and verdicts["DDDDDDDDDD"].code_here == "DDDDDDDDDD"


@pytest.mark.db
async def test_files_are_taken_under_their_codes_or_shared(db, tmp_path):
    here = await file_register_bytes(b"same", store="public", owner=HERE, filename="a.txt")
    taken_by_other = await file_register_bytes(b"other", store="public", owner=HERE, filename="b.txt")
    path = _archive_with(tmp_path / "a.tst", {
        "EEEEEEEEEE": b"new bytes", here.code: b"same", taken_by_other.code: b"different",
    })
    items = [
        _archived("EEEEEEEEEE", b"new bytes"),
        _archived(here.code, b"same"),
        _archived(taken_by_other.code, b"different"),
    ]
    verdicts = await judge_files(items, store="public")

    with ArchiveReader(path, FORMAT, max_file_bytes=1 << 20) as reader:
        reader.open_manifest()
        created = await take_file(reader, verdicts["EEEEEEEEEE"], owner=TASK, store="public")
        shared = await take_file(reader, verdicts[here.code], owner=TASK, store="public")
        renewed = await take_file(reader, verdicts[taken_by_other.code], owner=TASK, store="public")

    assert created.code == "EEEEEEEEEE"
    assert shared.code == here.code
    assert renewed.code not in (taken_by_other.code, here.code)
    assert {o.owner for o in await file_owners(here.code)} == {HERE, TASK}

    await release_taken([(created.code, TASK), (shared.code, TASK), (renewed.code, TASK)])

    assert {o.owner for o in await file_owners(here.code)} == {HERE}
    assert await file_owners(created.code) == []
    assert (await file_get(taken_by_other.code)).code == taken_by_other.code


@pytest.mark.db
async def test_a_soft_deleted_file_with_the_content_is_revived(db, tmp_path):
    binned = await file_register_bytes(b"binned", store="public", owner=HERE, filename="a.txt")
    await file_delete(binned.code)
    path = _archive_with(tmp_path / "a.tst", {binned.code: b"binned"})
    verdicts = await judge_files([_archived(binned.code, b"binned")], store="public")

    with ArchiveReader(path, FORMAT, max_file_bytes=1 << 20) as reader:
        reader.open_manifest()
        stored = await take_file(reader, verdicts[binned.code], owner=TASK, store="public")

    assert stored.code == binned.code
    assert (await file_get(binned.code)).deleted_at is None


@pytest.mark.db
async def test_the_installation_keeps_one_id(db):
    first = await install_id()

    assert first and await install_id() == first


async def _body(*parts: bytes):
    for part in parts:
        yield part


@pytest.mark.pure
async def test_an_upload_is_found_by_its_id_and_dropped(transfer_folder):
    area = UploadArea("tasks", ".utsk")

    stored = await area.take(_body(b"abc", b"def"), "Задача.utsk")
    found = area.get(stored.upload_id)

    assert found.file_name == "Задача.utsk" and found.size == 6
    assert found.path.read_bytes() == b"abcdef"
    assert found.path.parent == transfer_folder / "tasks" / "import"

    area.drop(stored.upload_id)
    with pytest.raises(TransferError) as caught:
        area.get(stored.upload_id)
    assert caught.value.code == errors.UPLOAD_NOT_FOUND


@pytest.mark.pure
@pytest.mark.parametrize("upload_id", ["../../etc/passwd", "", "01J0000000000000000000000l"])
def test_an_id_of_another_shape_is_a_miss(transfer_folder, upload_id):
    with pytest.raises(TransferError) as caught:
        UploadArea("tasks", ".utsk").get(upload_id)

    assert caught.value.code == errors.UPLOAD_NOT_FOUND


@pytest.mark.pure
async def test_an_upload_of_one_consumer_is_not_another_s(transfer_folder):
    stored = await UploadArea("tasks", ".utsk").take(_body(b"x"), "a.utsk")

    with pytest.raises(TransferError):
        UploadArea("codex", ".ucdx").get(stored.upload_id)


@pytest.mark.pure
async def test_an_oversized_upload_leaves_nothing(transfer_folder, monkeypatch):
    from src.modules.core_transfer import uploads

    monkeypatch.setattr(uploads, "MAX_UPLOAD_BYTES", 4)
    area = UploadArea("tasks", ".utsk")

    with pytest.raises(TransferError) as caught:
        await area.take(_body(b"abc", b"def"), "a.utsk")

    assert caught.value.code == errors.ARCHIVE_TOO_LARGE
    assert list((transfer_folder / "tasks" / "import").iterdir()) == []
