"""A codex carried whole between installations, and brought back where its codes are taken."""

from __future__ import annotations

import hashlib
import json
import shutil
import zipfile

import pytest
from sqlalchemy import func, select

from src.core.database import session_scope
from src.modules.codex.crud import codex as codex_crud
from src.modules.codex.crud import note as note_crud
from src.modules.codex.crud import transfer as transfer_crud
from src.modules.codex.file_owner import note_owner
from src.modules.codex.models import Codex, CodexMount, CodexNote
from src.modules.codex.transfer import apply as apply_module
from src.modules.codex.transfer.apply import free_segment
from src.modules.codex.transfer.collect import export_codex
from src.modules.codex.transfer.runner import analyze_archive, import_archive
from src.modules.core_storage.services.files import file_get, file_path
from src.modules.core_storage.services.ownership import file_owners
from src.modules.core_transfer import errors
from src.modules.core_transfer.errors import TransferError
from src.modules.core_transfer.rows import row_to_json
from src.modules.workspace.crud.workspace import workspace_create

from .conftest import make_rich_codex

pytestmark = pytest.mark.db


async def _snapshot(codex_code: str) -> dict:
    codex = await codex_crud.codex_get(codex_code, include_deleted=True)
    notes = await transfer_crud.notes_of(codex_code)
    bindings = await transfer_crud.bindings_of(note.code for note in notes)
    return {
        "codex": row_to_json(codex, omit=("updated_at",)),
        "notes": {note.code: row_to_json(note, omit=("updated_at",)) for note in notes},
        "files": {key: row_to_json(row, omit=("updated_at",)) for key, row in bindings.items()},
    }


async def _import(path, *, workspace=None, decisions=None):
    plan = await analyze_archive(path)
    _, report = await import_archive(path, workspace_code=workspace, decisions=decisions or {}, plan_token=plan.token)
    return plan, report


async def _carry(rich, tmp_path, other_installation):
    exported = await export_codex(rich.codex, tmp_path / "a.ucdx")
    kept = tmp_path / "kept.ucdx"
    shutil.copy(exported.path, kept)
    before = await _snapshot(rich.codex)
    payloads = {code: file_path(await file_get(code)).read_bytes()
                for code in (rich.image, rich.deep_file, rich.shared_file, rich.binned_file)}
    await other_installation()
    workspace = (await workspace_create(title="Там")).code
    return kept, before, payloads, workspace


async def test_the_archive_holds_the_whole_codex(rich, tmp_path):
    exported = await export_codex(rich.codex, tmp_path / "a.ucdx")

    with zipfile.ZipFile(exported.path) as archive:
        manifest = json.loads(archive.read("manifest.json"))
        notes = [json.loads(line) for line in archive.read("rows/notes.jsonl").decode().splitlines() if line]
        names = set(archive.namelist())

    codes = [row["code"] for row in notes]
    assert set(codes) == {rich.top, rich.second, rich.third, rich.fourth, rich.sibling, rich.binned}
    # Parents always before their children.
    assert codes.index(rich.top) < codes.index(rich.second) < codes.index(rich.third)
    assert manifest["counts"] == {"notes": 6, "deleted_notes": 1, "files": 5}
    assert manifest["dangling_refs"] == ["TASK@0123456789"]
    assert "rows/codex.jsonl" in names and f"bodies/codex/{rich.codex}.md" in names
    assert not any("mount" in name for name in names)
    assert exported.file_name == "Python.ucdx"


async def test_the_codex_comes_back_whole_in_another_installation(rich, tmp_path, other_installation):
    path, before, payloads, workspace = await _carry(rich, tmp_path, other_installation)

    plan, report = await _import(path, workspace=workspace)

    assert plan.conflicts == [] and report.recoded == [] and report.repathed == []
    assert await _snapshot(rich.codex) == before
    for code, payload in payloads.items():
        assert file_path(await file_get(code)).read_bytes() == payload
    assert {o.owner for o in await file_owners(rich.shared_file)} == {note_owner(rich.second), note_owner(rich.fourth)}
    assert report.mounted is True
    async with session_scope() as s:
        mounts = (await s.execute(select(CodexMount))).scalars().all()
    assert [(m.codex_code, m.workspace_code, m.enabled) for m in mounts] == [(rich.codex, workspace, True)]


async def test_without_a_workspace_nothing_is_mounted(rich, tmp_path, other_installation):
    path, _, _, _ = await _carry(rich, tmp_path, other_installation)

    _, report = await _import(path)

    assert report.mounted is False
    async with session_scope() as s:
        assert (await s.execute(select(func.count()).select_from(CodexMount))).scalar_one() == 0


async def test_a_reimport_names_the_codex_and_every_record_with_dates(rich, tmp_path):
    exported = await export_codex(rich.codex, tmp_path / "a.ucdx")

    plan = await analyze_archive(exported.path)

    by_id = {c.id: c for c in plan.conflicts}
    assert set(by_id) == {f"CODEX@{code}" for code in (rich.codex, rich.top, rich.second, rich.third,
                                                       rich.fourth, rich.sibling, rich.binned)}
    assert by_id[f"CODEX@{rich.codex}"].options == ("update", "replace")
    assert by_id[f"CODEX@{rich.top}"].requires == (f"CODEX@{rich.codex}", "update")
    dates = by_id[f"CODEX@{rich.top}"].as_dict()["dates"]
    assert dates["local"]["updated_at"] and dates["archive"]["updated_at"]


async def test_update_keeps_codes_and_what_is_only_here(rich, tmp_path):
    exported = await export_codex(rich.codex, tmp_path / "a.ucdx")
    await codex_crud.codex_update(rich.codex, title="Правлено")
    extra = await note_crud.note_create(parent_code=rich.top, segment="local", title="Только здесь")
    plan = await analyze_archive(exported.path)

    _, report = await import_archive(exported.path, workspace_code=rich.workspace,
                                     decisions={c.id: "update" for c in plan.conflicts}, plan_token=plan.token)

    assert (await codex_crud.codex_get(rich.codex)).title == "Python"
    assert await note_crud.note_get(extra.code) is not None
    assert report.recoded == [] and report.repathed == []
    async with session_scope() as s:
        assert (await s.execute(select(func.count()).select_from(Codex))).scalar_one() == 1


async def test_replace_makes_a_copy_with_a_free_path_and_moved_references(rich, tmp_path):
    exported = await export_codex(rich.codex, tmp_path / "a.ucdx")
    plan = await analyze_archive(exported.path)

    _, report = await import_archive(exported.path, workspace_code=None,
                                     decisions={c.id: "replace" for c in plan.conflicts}, plan_token=plan.token)

    moved = {row["from"]: row["to"] for row in report.recoded}
    copy = moved[f"CODEX@{rich.codex}"].split("@")[1]
    assert report.segment == "python-2"
    assert report.repathed == [{"entity": "codex", "title": "Python", "from": "/python", "to": "/python-2"}]
    rules = (await codex_crud.codex_get(copy)).body
    assert moved[f"CODEX@{rich.top}"] in rules and f"IMAGE@{rich.image}" in rules
    top_copy = moved[f"CODEX@{rich.top}"].split("@")[1]
    body = (await note_crud.note_get(top_copy)).body
    assert moved[f"CODEX@{rich.second}"] in body and moved[f"CODEX@{rich.third}"] in body
    # The original is untouched.
    assert (await codex_crud.codex_get(rich.codex)).segment == "python"


async def test_a_record_of_another_codex_offers_replace_only(rich, tmp_path):
    exported = await export_codex(rich.codex, tmp_path / "a.ucdx")
    other = (await codex_crud.codex_create(segment="go", title="Go")).code
    await note_crud.note_update(rich.fourth, parent_code=other)

    plan = await analyze_archive(exported.path)

    moved = next(c for c in plan.conflicts if c.id == f"CODEX@{rich.fourth}")
    assert moved.options == ("replace",) and moved.reason == "record_other_codex"
    assert moved.reason_params == {"codex": "Go"}


async def test_a_record_cannot_be_updated_without_its_codex(rich, tmp_path):
    exported = await export_codex(rich.codex, tmp_path / "a.ucdx")
    plan = await analyze_archive(exported.path)
    decisions = {c.id: "replace" for c in plan.conflicts} | {f"CODEX@{rich.top}": "update"}

    with pytest.raises(TransferError) as caught:
        await import_archive(exported.path, workspace_code=None, decisions=decisions, plan_token=plan.token)

    assert caught.value.code == errors.DECISION_INVALID
    async with session_scope() as s:
        assert (await s.execute(select(func.count()).select_from(Codex))).scalar_one() == 1


async def test_a_taken_sibling_segment_gets_a_suffix(rich, tmp_path, other_installation):
    path, _, _, workspace = await _carry(rich, tmp_path, other_installation)
    # The codex arrives in an installation where it already exists with another code and its own records.
    await make_rich_codex(segment="python", workspace_title="Здесь")

    plan, report = await _import(path, workspace=workspace)

    assert plan.conflicts == []
    assert report.segment == "python-2"


async def test_a_failure_in_the_rows_leaves_nothing(rich, tmp_path, other_installation, monkeypatch):
    path, _, _, workspace = await _carry(rich, tmp_path, other_installation)

    async def broken(*_args, **_kwargs):
        raise RuntimeError("the rows failed")

    monkeypatch.setattr(apply_module, "_write", broken)
    plan = await analyze_archive(path)

    with pytest.raises(RuntimeError):
        await import_archive(path, workspace_code=workspace, decisions={}, plan_token=plan.token)

    async with session_scope() as s:
        assert (await s.execute(select(func.count()).select_from(CodexNote))).scalar_one() == 0
    for code in (rich.image, rich.deep_file, rich.shared_file):
        assert await file_owners(code) == []


def _with_row_changed(source, target, entry: str, change) -> None:
    """A copy whose first row of ``entry`` is changed and whose inventory still matches."""
    with zipfile.ZipFile(source) as old:
        rows = [json.loads(line) for line in old.read(entry).decode().splitlines() if line]
        change(rows[0])
        payload = "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows).encode()
        manifest = json.loads(old.read("manifest.json"))
        for item in manifest["files"]:
            if item["path"] == entry:
                item["bytes"], item["sha256"] = len(payload), hashlib.sha256(payload).hexdigest()
        with zipfile.ZipFile(target, "w") as new:
            for info in old.infolist():
                data = {"manifest.json": json.dumps(manifest).encode(), entry: payload}.get(info.filename)
                new.writestr(info, data if data is not None else old.read(info.filename))


@pytest.mark.parametrize(("entry", "change", "detail"), [
    ("rows/notes.jsonl", lambda row: row.update(sort="x"), "codex_note.sort"),
    ("rows/notes.jsonl", lambda row: row.update(description=None), "codex_note.description"),
    ("rows/codex.jsonl", lambda row: row.update(sort=False), "codex.sort"),
    ("rows/files.jsonl", lambda row: row["binding"].update(title=7), "codex_file.title"),
])
async def test_a_value_that_does_not_fit_its_column_is_refused_at_the_plan(
    rich, tmp_path, other_installation, entry, change, detail,
):
    path, _, _, _ = await _carry(rich, tmp_path, other_installation)
    crafted = tmp_path / "crafted.ucdx"
    _with_row_changed(path, crafted, entry, change)

    with pytest.raises(TransferError) as refused:
        await analyze_archive(crafted)

    assert refused.value.code == errors.ARCHIVE_INCONSISTENT
    assert detail in refused.value.params["detail"]
    async with session_scope() as s:
        assert (await s.execute(select(func.count()).select_from(CodexNote))).scalar_one() == 0


@pytest.mark.pure
def test_a_free_segment_is_found_within_the_width():
    assert free_segment("python", set()) == "python"
    assert free_segment("python", {"python", "python-2"}) == "python-3"
    long = "a" * 64
    assert free_segment(long, {long}) == "a" * 62 + "-2"


async def test_the_routes_end_to_end(client, rich, other_installation):
    response = await client.get(f"/internal/codex/codexes/CODEX@{rich.codex}/export")
    assert response.status_code == 200
    assert response.headers["content-type"] == "application/vnd.uroboros.codex+zip"
    payload = response.content
    await other_installation()
    workspace = (await workspace_create(title="Там")).code

    upload = (await client.post("/internal/codex/transfer/upload", params={"filename": "Python.ucdx"},
                                content=payload)).json()["upload_id"]
    plan = (await client.post(f"/internal/codex/transfer/{upload}/analyze", json={})).json()
    applied = await client.post(f"/internal/codex/transfer/{upload}/apply", json={
        "workspace": f"WORKSPACE@{workspace}", "decisions": {}, "plan_token": plan["plan_token"],
    })

    assert plan["root"] == {"code": f"CODEX@{rich.codex}", "title": "Python", "path": "/python", "deleted": False}
    assert plan["counts"] == {"notes": 6, "deleted_notes": 1, "files": 4}
    assert applied.status_code == 200, applied.text
    assert applied.json()["codex"]["code"] == f"CODEX@{rich.codex}" and applied.json()["mounted"] is True

    hostile = (await client.post("/internal/codex/transfer/upload", content=b"not a zip")).json()["upload_id"]
    refused = await client.post(f"/internal/codex/transfer/{hostile}/analyze", json={})
    assert (refused.status_code, refused.json()["code"]) == (400, "transfer_not_archive")


async def test_a_task_archive_is_not_a_codex(client, rich, tmp_path):
    from src.modules.core_transfer.container import ArchiveWriter
    from src.modules.core_transfer.manifest import ManifestRoot, ManifestSource
    from src.modules.tasks.transfer.constants import TASK_ARCHIVE

    path = tmp_path / "a.utsk"
    with ArchiveWriter(path, TASK_ARCHIVE) as archive:
        archive.finish(archive_id="01J00000000000000000000000", source=ManifestSource(),
                       root=ManifestRoot(code="0123456789"), counts={}, dangling_refs=[])
    upload = (await client.post("/internal/codex/transfer/upload", content=path.read_bytes())).json()["upload_id"]

    refused = await client.post(f"/internal/codex/transfer/{upload}/analyze", json={})

    assert (refused.status_code, refused.json()["code"]) == (400, "transfer_not_archive")
