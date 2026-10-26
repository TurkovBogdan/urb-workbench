"""Files in a codex transfer, scenario by scenario — by the storage's rows, owners and bindings.

The same rule as for a task: «code + sha256»; the same bytes are never a conflict; a code holding
other bytes brings the archive's as a new file; a row's claim about a file is trusted only as far
as the bytes the archive carries.
"""

from __future__ import annotations

import hashlib
import json
import shutil
import zipfile
from pathlib import Path

import pytest
from sqlalchemy import func, select

from src.core.database import session_scope
from src.modules.codex.crud import codex as codex_crud
from src.modules.codex.crud import note as note_crud
from src.modules.codex.crud import transfer as transfer_crud
from src.modules.codex.file_owner import note_owner
from src.modules.codex.files import codex_file_retitle
from src.modules.codex.transfer import apply as apply_module
from src.modules.codex.transfer.collect import export_codex
from src.modules.codex.transfer.runner import analyze_archive, import_archive
from src.modules.core_storage import settings as storage_settings
from src.modules.core_storage.dto import Owner
from src.modules.core_storage.models import CoreStorageFile
from src.modules.core_storage.services.files import file_get, file_path
from src.modules.core_storage.services.ownership import file_owners
from src.modules.core_storage.services.registration import file_register_path
from src.modules.core_transfer import errors
from src.modules.core_transfer.errors import TransferError
from src.modules.workspace.crud.workspace import workspace_create

from ..file_support import codex_file_attach_bytes
from .conftest import PNG

pytestmark = pytest.mark.db


async def _owners(code: str) -> set[Owner]:
    return {place.owner for place in await file_owners(code)}


async def _stored_count() -> int:
    async with session_scope() as s:
        return (await s.execute(select(func.count()).select_from(CoreStorageFile))).scalar_one()


async def _import(path, *, workspace=None, decisions=None):
    plan = await analyze_archive(path)
    _, report = await import_archive(path, workspace_code=workspace, decisions=decisions or {}, plan_token=plan.token)
    return plan, report


async def _carried(rich, tmp_path, other_installation) -> Path:
    exported = await export_codex(rich.codex, tmp_path / "a.ucdx")
    kept = tmp_path / "kept.ucdx"
    shutil.copy(exported.path, kept)
    await other_installation()
    return kept


def _rows(path: Path, entry: str) -> list[dict]:
    with zipfile.ZipFile(path) as archive:
        return [json.loads(line) for line in archive.read(entry).decode().split("\n") if line]


def _rewrite(source: Path, target: Path, entry: str, rows: list[dict]) -> Path:
    payload = "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows).encode()
    with zipfile.ZipFile(source) as old:
        manifest = json.loads(old.read("manifest.json"))
        for item in manifest["files"]:
            if item["path"] == entry:
                item["bytes"], item["sha256"] = len(payload), hashlib.sha256(payload).hexdigest()
        with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as new:
            for info in old.infolist():
                data = {"manifest.json": json.dumps(manifest).encode(), entry: payload}.get(info.filename)
                new.writestr(zipfile.ZipInfo(info.filename), data if data is not None else old.read(info.filename),
                             compress_type=info.compress_type)
    return target


async def _a_record_here() -> str:
    codex = await codex_crud.codex_create(segment="local", title="Здешняя")
    return (await note_crud.note_create(parent_code=codex.code, segment="n", title="Здешняя запись")).code


async def test_every_file_comes_back_with_its_code_bytes_and_record(rich, tmp_path, other_installation):
    payloads = {code: file_path(await file_get(code)).read_bytes()
                for code in (rich.image, rich.deep_file, rich.shared_file, rich.binned_file)}
    path = await _carried(rich, tmp_path, other_installation)

    await _import(path)

    for code, payload in payloads.items():
        assert file_path(await file_get(code)).read_bytes() == payload
    bindings = await transfer_crud.bindings_of([rich.top, rich.third, rich.second, rich.fourth, rich.binned])
    assert set(bindings) == {
        (rich.top, rich.image), (rich.third, rich.deep_file), (rich.second, rich.shared_file),
        (rich.fourth, rich.shared_file), (rich.binned, rich.binned_file),
    }
    # The bin keeps its file: a restored record finds it in place.
    assert note_owner(rich.binned) in await _owners(rich.binned_file)
    assert bindings[(rich.fourth, rich.shared_file)].title == "Общий"
    names = {p.owner: p.original_filename + p.original_extension for p in await file_owners(rich.image)}
    assert names[note_owner(rich.top)] == "shot.png"


async def test_the_same_bytes_under_another_code_are_reused_and_the_rules_follow(rich, tmp_path, other_installation):
    path = await _carried(rich, tmp_path, other_installation)
    record = await _a_record_here()
    here = await codex_file_attach_bytes(record, PNG, filename="local.png")
    files_before = await _stored_count()

    plan, report = await _import(path)

    assert not any(c.id.startswith("FILE@") for c in plan.conflicts)
    assert await _stored_count() == files_before + 3
    assert await _owners(here.file_code) == {note_owner(record), note_owner(rich.top)}
    rules = (await codex_crud.codex_get(rich.codex)).body
    assert f"IMAGE@{here.file_code}" in rules and f"IMAGE@{rich.image}" not in rules
    assert {"entity": "file", "title": "Скриншот", "from": f"FILE@{rich.image}", "to": f"FILE@{here.file_code}"} in report.recoded


async def test_a_code_holding_other_bytes_brings_a_new_file(rich, tmp_path, other_installation):
    path = await _carried(rich, tmp_path, other_installation)
    source = tmp_path / "other.bin"
    source.write_bytes(b"other content entirely")
    forced = await file_register_path(source, store="public", owner=Owner("X", "1"), preferred_code=rich.deep_file)
    assert forced.code == rich.deep_file

    plan, report = await _import(path)

    conflict = next(c for c in plan.conflicts if c.id == f"FILE@{rich.deep_file}")
    assert conflict.options == ("replace",) and conflict.reason == "file_other_content"
    new_code = next(r["to"] for r in report.recoded if r["from"] == f"FILE@{rich.deep_file}").split("@")[1]
    assert file_path(await file_get(new_code)).read_bytes() == b"deep bytes"
    assert file_path(await file_get(rich.deep_file)).read_bytes() == b"other content entirely"
    assert f"FILE@{new_code}" in (await note_crud.note_get(rich.top)).body


async def test_a_reimport_takes_no_bytes(rich, tmp_path):
    exported = await export_codex(rich.codex, tmp_path / "a.ucdx")
    files_before = await _stored_count()
    plan = await analyze_archive(exported.path)

    _, report = await import_archive(exported.path, workspace_code=None,
                                     decisions={c.id: "replace" for c in plan.conflicts}, plan_token=plan.token)

    assert await _stored_count() == files_before
    moved = {r["from"]: r["to"].split("@")[1] for r in report.recoded}
    assert await _owners(rich.shared_file) == {
        note_owner(rich.second), note_owner(rich.fourth),
        note_owner(moved[f"CODEX@{rich.second}"]), note_owner(moved[f"CODEX@{rich.fourth}"]),
    }


async def test_update_brings_the_binding_back_to_the_archive(rich, tmp_path):
    exported = await export_codex(rich.codex, tmp_path / "a.ucdx")
    await codex_file_retitle(rich.top, rich.image, title="Переименовано здесь")
    plan = await analyze_archive(exported.path)

    await import_archive(exported.path, workspace_code=None,
                         decisions={c.id: "update" for c in plan.conflicts if "update" in c.options},
                         plan_token=plan.token)

    assert (await transfer_crud.bindings_of([rich.top]))[(rich.top, rich.image)].title == "Скриншот"


async def test_a_failed_update_keeps_the_owners_the_records_had(rich, tmp_path, monkeypatch):
    exported = await export_codex(rich.codex, tmp_path / "a.ucdx")
    codes = (rich.image, rich.deep_file, rich.shared_file, rich.binned_file)
    before = {code: await _owners(code) for code in codes}

    async def broken(*_args, **_kwargs):
        raise RuntimeError("the rows failed")

    monkeypatch.setattr(apply_module, "_write", broken)
    plan = await analyze_archive(exported.path)

    with pytest.raises(RuntimeError):
        await import_archive(exported.path, workspace_code=None,
                             decisions={c.id: "update" for c in plan.conflicts if "update" in c.options},
                             plan_token=plan.token)

    assert {code: await _owners(code) for code in codes} == before


async def test_a_failed_replace_gives_back_only_what_it_took(rich, tmp_path, monkeypatch):
    exported = await export_codex(rich.codex, tmp_path / "a.ucdx")
    codes = (rich.image, rich.deep_file, rich.shared_file, rich.binned_file)
    before = {code: await _owners(code) for code in codes}

    async def broken(*_args, **_kwargs):
        raise RuntimeError("the rows failed")

    monkeypatch.setattr(apply_module, "_write", broken)
    plan = await analyze_archive(exported.path)

    with pytest.raises(RuntimeError):
        await import_archive(exported.path, workspace_code=None,
                             decisions={c.id: "replace" for c in plan.conflicts}, plan_token=plan.token)

    assert {code: await _owners(code) for code in codes} == before


async def test_the_bytes_of_a_content_here_are_never_read(rich, tmp_path, monkeypatch):
    from src.modules.core_transfer.container import ArchiveReader

    exported = await export_codex(rich.codex, tmp_path / "a.ucdx")
    seen: list[str] = []
    real = ArchiveReader.file_chunks

    def counting(self, entry: str):
        seen.append(entry)
        return real(self, entry)

    monkeypatch.setattr(ArchiveReader, "file_chunks", counting)
    plan = await analyze_archive(exported.path)

    await import_archive(exported.path, workspace_code=None,
                         decisions={c.id: "replace" for c in plan.conflicts}, plan_token=plan.token)

    assert seen == []


async def test_a_file_over_this_storage_ceiling_refuses_by_name(rich, tmp_path, other_installation, monkeypatch):
    path = await _carried(rich, tmp_path, other_installation)

    class Small:
        max_file_size_mb = 0

    monkeypatch.setattr(storage_settings, "_current", Small())

    with pytest.raises(TransferError) as caught:
        await analyze_archive(path)

    assert caught.value.code == errors.FILE_TOO_LARGE
    assert caught.value.params["name"] in {"shot.png", "a.txt", "s.txt", "b.txt"}
    assert await _stored_count() == 0


async def test_a_row_claiming_the_sum_of_a_file_here_takes_nothing(rich, tmp_path, other_installation):
    path = await _carried(rich, tmp_path, other_installation)
    record = await _a_record_here()
    victim = await codex_file_attach_bytes(record, b"secret codex bytes", filename="secret.txt")
    rows = _rows(path, "rows/files.jsonl")
    for row in rows:
        if row["binding"]["file_code"] == rich.deep_file:
            row["stored"]["sha256"] = hashlib.sha256(b"secret codex bytes").hexdigest()
            row["stored"]["size"] = len(b"secret codex bytes")
    crafted = _rewrite(path, tmp_path / "crafted.ucdx", "rows/files.jsonl", rows)

    with pytest.raises(TransferError) as caught:
        await analyze_archive(crafted)

    assert caught.value.code == errors.ARCHIVE_INCONSISTENT
    assert await _owners(victim.file_code) == {note_owner(record)}


async def test_imported_into_a_workspace_files_are_reachable_from_it(rich, tmp_path, other_installation):
    path = await _carried(rich, tmp_path, other_installation)
    workspace = (await workspace_create(title="Там")).code

    _, report = await _import(path, workspace=workspace)

    assert report.mounted
    # A file of a record of a mounted codex is what the workspace sees: owners are the records.
    assert note_owner(rich.third) in await _owners(rich.deep_file)
