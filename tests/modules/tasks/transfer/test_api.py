"""The routes of a task transfer, end to end over HTTP, and every refusal by the state it leaves."""

from __future__ import annotations

import io
import json
import zipfile
from urllib.parse import quote

import pytest
from sqlalchemy import func, select

from src.core.database import session_scope
from src.modules.core_storage.models import CoreStorageFile
from src.modules.tasks.crud import group as group_crud
from src.modules.tasks.crud import task as task_crud
from src.modules.tasks.models.task import TasksTask
from src.modules.workspace.crud.workspace import workspace_create

from .support import jsonl, read_rows, rewrite_archive

pytestmark = pytest.mark.db

BASE = "/internal/workbench"


async def _counts() -> tuple[int, int]:
    async with session_scope() as s:
        tasks = (await s.execute(select(func.count()).select_from(TasksTask))).scalar_one()
        files = (await s.execute(select(func.count()).select_from(CoreStorageFile))).scalar_one()
    return tasks, files


async def _export(client, code: str) -> bytes:
    response = await client.get(f"{BASE}/tasks/TASK@{code}/export")
    assert response.status_code == 200, response.text
    return response.content


async def _upload(client, payload: bytes, name: str = "a.utsk") -> str:
    response = await client.post(f"{BASE}/transfer/upload", params={"filename": name}, content=payload)
    assert response.status_code == 200, response.text
    return response.json()["upload_id"]


async def test_the_export_is_a_named_archive(client, rich):
    response = await client.get(f"{BASE}/tasks/TASK@{rich.root}/export")

    assert response.status_code == 200
    assert response.headers["content-type"] == "application/vnd.uroboros.task+zip"
    assert quote("Перенос задачи.utsk") in response.headers["content-disposition"]


async def test_a_deleted_or_unknown_task_is_not_exported(client, rich):
    await task_crud.task_delete(rich.child)

    deleted = await client.get(f"{BASE}/tasks/TASK@{rich.child}/export")
    unknown = await client.get(f"{BASE}/tasks/TASK@0000000000/export")

    assert (deleted.status_code, deleted.json()["code"]) == (409, "tasks.task.deleted")
    assert (unknown.status_code, unknown.json()["code"]) == (404, "tasks.task.not_found")


async def test_the_whole_import_into_another_installation(client, rich, other_installation):
    payload = await _export(client, rich.root)
    await other_installation()
    workspace = (await workspace_create(title="Там")).code
    group = (await group_crud.group_create(workspace_code=workspace, title="Сюда")).code

    upload = await _upload(client, payload, "Перенос задачи.utsk")
    plan = (await client.post(f"{BASE}/transfer/{upload}/analyze", json={"workspace": f"WORKSPACE@{workspace}"})).json()
    applied = await client.post(f"{BASE}/transfer/{upload}/apply", json={
        "workspace": f"WORKSPACE@{workspace}", "group_code": f"TASKGROUP@{group}",
        "decisions": {}, "plan_token": plan["plan_token"],
    })

    assert plan["archive"]["file_name"] == "Перенос задачи.utsk"
    assert plan["archive"]["same_install"] is False
    assert plan["archive"]["source_workspace"] == "Работа"
    assert plan["root"] == {"code": f"TASK@{rich.root}", "title": "Перенос задачи", "subtasks": 1}
    assert plan["counts"] == {"tasks": 2, "stages": 3, "journal": 3, "notes": 3, "files": 4}
    assert plan["conflicts"] == []
    assert plan["notices"]["dangling_refs"] == [f"TASK@{rich.outside}"]
    assert applied.status_code == 200, applied.text
    assert applied.json()["task"] == {"code": f"TASK@{rich.root}", "title": "Перенос задачи"}
    assert (await task_crud.task_get(rich.root)).group_code == group
    # The upload is gone once applied.
    again = await client.post(f"{BASE}/transfer/{upload}/analyze", json={"workspace": workspace})
    assert (again.status_code, again.json()["code"]) == (404, "transfer_upload_not_found")


async def test_a_reimport_shows_conflicts_with_dates(client, rich):
    upload = await _upload(client, await _export(client, rich.root))

    plan = (await client.post(f"{BASE}/transfer/{upload}/analyze", json={"workspace": rich.workspace})).json()

    root = next(c for c in plan["conflicts"] if c["id"] == f"TASK@{rich.root}")
    assert root["options"] == ["update", "replace"]
    assert root["local"]["title"] == "Перенос задачи"
    assert set(root["dates"]) == {"local", "archive"}
    assert root["dates"]["local"]["updated_at"]

    missing = await client.post(f"{BASE}/transfer/{upload}/apply", json={
        "workspace": rich.workspace, "decisions": {}, "plan_token": plan["plan_token"],
    })
    assert (missing.status_code, missing.json()["code"]) == (422, "transfer_decision_invalid")

    stale = await client.post(f"{BASE}/transfer/{upload}/apply", json={
        "workspace": rich.workspace, "decisions": {}, "plan_token": "0" * 64,
    })
    assert (stale.status_code, stale.json()["code"]) == (409, "transfer_plan_changed")


def _tampered(payload: bytes, tmp_path, *, replace: dict[str, bytes] | None = None,
              add: dict[str, bytes] | None = None) -> bytes:
    source = tmp_path / "in.utsk"
    source.write_bytes(payload)
    target = tmp_path / "out.utsk"
    with zipfile.ZipFile(source) as old, zipfile.ZipFile(target, "w") as new:
        for info in old.infolist():
            data = (replace or {}).get(info.filename, old.read(info.filename))
            new.writestr(info.filename, data, compress_type=info.compress_type)
        for name, data in (add or {}).items():
            new.writestr(name, data)
    return target.read_bytes()


@pytest.mark.parametrize("case", ["not_zip", "mimetype", "extra_entry", "damaged", "newer", "codex"])
async def test_a_hostile_archive_is_refused_and_writes_nothing(client, rich, tmp_path, other_installation, case):
    payload = await _export(client, rich.root)
    with zipfile.ZipFile(io.BytesIO(payload)) as archive:
        manifest = json.loads(archive.read("manifest.json"))
    variants = {
        "not_zip": (b"not an archive", "transfer_not_archive"),
        "mimetype": (_tampered(payload, tmp_path, replace={"mimetype": b"application/zip"}), "transfer_not_archive"),
        "extra_entry": (_tampered(payload, tmp_path, add={"evil.sh": b"rm -rf"}), "transfer_entry_not_allowed"),
        "damaged": (_tampered(payload, tmp_path, replace={"rows/tasks.jsonl": b"{}\n"}), "transfer_entry_damaged"),
        "newer": (_tampered(payload, tmp_path, replace={"manifest.json": json.dumps({**manifest, "format_version": 9}).encode()}),
                  "transfer_newer_format"),
        "codex": (_tampered(payload, tmp_path, replace={"manifest.json": json.dumps({**manifest, "format": "uroboros.codex"}).encode()}),
                  "transfer_foreign_format"),
    }
    body, code = variants[case]
    await other_installation()
    workspace = (await workspace_create(title="Там")).code
    before = await _counts()

    upload = await _upload(client, body)
    response = await client.post(f"{BASE}/transfer/{upload}/analyze", json={"workspace": workspace})

    assert (response.status_code, response.json()["code"]) == (400, code)
    assert await _counts() == before


def _retyped(row: dict, path: tuple[str, ...], value) -> dict:
    target = row
    for key in path[:-1]:
        target = target[key]
    if value is _ABSENT:
        del target[path[-1]]
    else:
        target[path[-1]] = value
    return row


_ABSENT = object()


@pytest.mark.parametrize(("entry", "path", "value", "detail"), [
    ("links", ("sort",), "abc", "position"),
    ("links", ("sort",), _ABSENT, "position"),
    ("notes", ("link", "sort"), True, "position"),
    ("stages", ("title",), 5, "tasks_stage.title"),
    ("journal", ("title",), None, "tasks_journal.title"),
    ("files", ("binding", "sort"), "1", "tasks_file.sort"),
    ("tasks", ("description",), {"x": 1}, "tasks.description"),
])
async def test_a_value_that_does_not_fit_its_column_is_refused_at_the_plan(
    client, rich, tmp_path, other_installation, entry, path, value, detail,
):
    """SQLite would keep a word in a number column and PostgreSQL would fail mid-write: both refuse
    the archive at the plan instead, before any file is taken."""
    source = tmp_path / "in.utsk"
    source.write_bytes(await _export(client, rich.root))
    rows = read_rows(source, f"rows/{entry}.jsonl")
    rows[0] = _retyped(rows[0], path, value)
    crafted = rewrite_archive(source, tmp_path / "out.utsk", {f"rows/{entry}.jsonl": jsonl(rows)})
    await other_installation()
    workspace = (await workspace_create(title="Там")).code
    before = await _counts()

    upload = await _upload(client, crafted.read_bytes())
    response = await client.post(f"{BASE}/transfer/{upload}/analyze", json={"workspace": workspace})

    assert (response.status_code, response.json()["code"]) == (400, "transfer_archive_inconsistent")
    assert detail in response.json()["params"]["detail"]
    assert await _counts() == before


async def test_a_group_of_another_workspace_is_refused(client, rich, other_installation):
    payload = await _export(client, rich.root)
    await other_installation()
    workspace = (await workspace_create(title="Там")).code
    foreign = (await group_crud.group_create(
        workspace_code=(await workspace_create(title="Чужое")).code, title="Не тут",
    )).code
    upload = await _upload(client, payload)
    plan = (await client.post(f"{BASE}/transfer/{upload}/analyze", json={"workspace": workspace})).json()
    before = await _counts()

    response = await client.post(f"{BASE}/transfer/{upload}/apply", json={
        "workspace": workspace, "group_code": foreign, "decisions": {}, "plan_token": plan["plan_token"],
    })

    assert (response.status_code, response.json()["code"]) == (404, "tasks.group.not_found")
    assert await _counts() == before


async def test_cancel_removes_the_upload(client, rich, transfer_folder):
    upload = await _upload(client, await _export(client, rich.root))

    response = await client.delete(f"{BASE}/transfer/{upload}")

    assert response.status_code == 204
    assert list((transfer_folder / "tasks" / "import").iterdir()) == []


async def test_an_unknown_workspace_is_refused(client, rich):
    upload = await _upload(client, await _export(client, rich.root))

    response = await client.post(f"{BASE}/transfer/{upload}/analyze", json={"workspace": "0000000000"})

    assert (response.status_code, response.json()["code"]) == (404, "workspace.workspace.not_found")


async def test_an_unknown_field_is_refused(client, rich):
    upload = await _upload(client, await _export(client, rich.root))

    response = await client.post(f"{BASE}/transfer/{upload}/analyze", json={"workspace": rich.workspace, "x": 1})

    assert response.status_code == 422
