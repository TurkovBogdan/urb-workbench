"""The export: what a ``.utsk`` holds of a task «with everything», and what it leaves behind."""

from __future__ import annotations

import hashlib
import json
import zipfile

import pytest

from src.modules.core_storage.services.files import file_get, file_path
from src.modules.tasks.transfer.collect import export_task

pytestmark = pytest.mark.db


def _rows(archive: zipfile.ZipFile, entity: str) -> list[dict]:
    return [json.loads(line) for line in archive.read(f"rows/{entity}.jsonl").decode().split("\n") if line]


async def test_the_archive_holds_the_task_with_everything(rich, tmp_path):
    exported = await export_task(rich.root, tmp_path / "a.utsk")

    with zipfile.ZipFile(exported.path) as archive:
        names = set(archive.namelist())
        tasks = _rows(archive, "tasks")
        links = _rows(archive, "links")
        stages = _rows(archive, "stages")
        journal = _rows(archive, "journal")
        notes = _rows(archive, "notes")
        files = _rows(archive, "files")
        manifest = json.loads(archive.read("manifest.json"))

    assert [row["code"] for row in tasks] == [rich.root, rich.child]
    assert links == [{**links[0], "task_code": rich.child, "parent_code": rich.root}]
    assert {row["code"] for row in stages} == {*rich.stages, rich.child_stage}
    assert {row["code"] for row in journal} == set(rich.entries)
    assert {row["note"]["code"] for row in notes} == {*rich.notes, rich.child_note}
    # One binding per task: the shared file is held by both, its bytes travel once.
    assert sorted((row["binding"]["task_code"], row["binding"]["file_code"]) for row in files) == sorted([
        (rich.root, rich.task_file), (rich.root, rich.note_file), (rich.root, rich.stage_file),
        (rich.root, rich.shared_file), (rich.child, rich.shared_file),
    ])
    assert sum(1 for name in names if name.startswith("files/")) == 4
    assert manifest["root"]["code"] == rich.root
    assert manifest["counts"] == {"tasks": 2, "stages": 3, "journal": 3, "notes": 3, "files": 5}
    assert manifest["dangling_refs"] == [f"TASK@{rich.outside}"]


async def test_neither_the_group_nor_the_workspace_travels(rich, tmp_path):
    exported = await export_task(rich.root, tmp_path / "a.utsk")

    with zipfile.ZipFile(exported.path) as archive:
        tasks = _rows(archive, "tasks")
        raw = b"".join(archive.read(name) for name in archive.namelist() if name.startswith("rows/"))

    assert all("group_code" not in row and "workspace_code" not in row for row in tasks)
    assert rich.group.encode() not in raw


async def test_deleted_subtasks_and_notes_stay_behind(rich, tmp_path):
    exported = await export_task(rich.root, tmp_path / "a.utsk")

    with zipfile.ZipFile(exported.path) as archive:
        content = b"".join(archive.read(name) for name in archive.namelist())

    assert rich.deleted_child.encode() not in content
    assert rich.deleted_note.encode() not in content


async def test_the_bytes_travel_whole(rich, tmp_path):
    exported = await export_task(rich.root, tmp_path / "a.utsk")
    stored = await file_get(rich.task_file)

    with zipfile.ZipFile(exported.path) as archive:
        payload = archive.read(f"files/{rich.task_file}{stored.extension}")

    assert hashlib.sha256(payload).hexdigest() == stored.sha256
    assert payload == file_path(stored).read_bytes()


async def test_a_subtask_travels_alone(rich, tmp_path):
    exported = await export_task(rich.child, tmp_path / "a.utsk")

    with zipfile.ZipFile(exported.path) as archive:
        tasks = _rows(archive, "tasks")
        links = _rows(archive, "links")

    assert [row["code"] for row in tasks] == [rich.child]
    assert links == []


async def test_the_file_is_named_by_the_title(rich, tmp_path):
    exported = await export_task(rich.root, tmp_path / "a.utsk")

    assert exported.file_name == "Перенос задачи.utsk"
