"""Files in a task transfer, scenario by scenario — checked by the storage's rows and owners and by
the bindings, not by the answer.

The rule they all follow: a file is judged by «code + sha256». The same bytes are never a conflict
— they are skipped and only the binding is written; a code holding other bytes brings the archive's
as a new file; nothing a row claims about a file is trusted beyond the bytes the archive carries.
"""

from __future__ import annotations

import hashlib
import shutil

import pytest
from sqlalchemy import func, select

from src.core.database import session_scope
from src.modules.core_storage import settings as storage_settings
from src.modules.core_storage.dto import Owner
from src.modules.core_storage.models import CoreStorageFile
from src.modules.core_storage.services.files import file_delete, file_get
from src.modules.core_storage.services.ownership import file_owners
from src.modules.core_transfer import errors
from src.modules.core_transfer.errors import TransferError
from src.modules.notes.crud.note import note_delete
from src.modules.tasks.crud import note as note_crud
from src.modules.tasks.crud import task as task_crud
from src.modules.tasks.crud import transfer as transfer_crud
from src.modules.tasks.file_owner import task_owner
from src.modules.tasks.files import FilePlace, task_file_retitle
from src.modules.tasks.transfer import apply as apply_module
from src.modules.tasks.transfer.collect import export_task
from src.modules.tasks.transfer.runner import analyze_archive, import_archive
from src.modules.workspace.crud.workspace import workspace_create

from ..file_support import task_file_attach_bytes
from .conftest import PNG
from .support import jsonl, read_rows, rewrite_archive, run_import

pytestmark = pytest.mark.db


async def _owners(code: str) -> set[Owner]:
    return {place.owner for place in await file_owners(code)}


async def _stored_count() -> int:
    async with session_scope() as s:
        return (await s.execute(select(func.count()).select_from(CoreStorageFile))).scalar_one()


async def _carried(rich, tmp_path, other_installation):
    exported = await export_task(rich.root, tmp_path / "a.utsk")
    kept = tmp_path / "kept.utsk"
    shutil.copy(exported.path, kept)
    await other_installation()
    workspace = (await workspace_create(title="Там")).code
    return kept, workspace


def _all(plan, choice: str) -> dict[str, str]:
    return {c.id: choice for c in plan.conflicts if choice in c.options}


@pytest.fixture
def read_entries(monkeypatch) -> list[str]:
    """Every file entry whose bytes the import reads out of the archive."""
    from src.modules.core_transfer.container import ArchiveReader

    seen: list[str] = []
    real = ArchiveReader.file_chunks

    def counting(self, entry: str):
        seen.append(entry)
        return real(self, entry)

    monkeypatch.setattr(ArchiveReader, "file_chunks", counting)
    return seen


# ── The same bytes ─────────────────────────────────────────────────────────────


async def test_the_bytes_of_a_content_here_are_never_read(rich, tmp_path, read_entries):
    exported = await export_task(rich.root, tmp_path / "a.utsk")
    plan = await analyze_archive(exported.path, workspace_code=rich.workspace)

    await import_archive(exported.path, workspace_code=rich.workspace, group_code=None,
                         decisions=_all(plan, "replace"), plan_token=plan.token)

    assert read_entries == []


async def test_only_the_bytes_not_here_are_read(rich, tmp_path, other_installation, read_entries):
    path, workspace = await _carried(rich, tmp_path, other_installation)
    holder = await task_crud.task_create(workspace_code=workspace, title="Здешняя")
    await task_file_attach_bytes(holder.code, PNG, filename="local.png")

    await run_import(path, workspace)

    read = {entry.split("/")[1].split(".")[0] for entry in read_entries}
    assert read == {rich.note_file, rich.stage_file, rich.shared_file}


async def test_the_same_bytes_under_another_code_are_reused_and_the_texts_follow(rich, tmp_path, other_installation):
    path, workspace = await _carried(rich, tmp_path, other_installation)
    # Here the picture and the note's file already lie under codes of their own.
    holder = await task_crud.task_create(workspace_code=workspace, title="Здешняя")
    here = await task_file_attach_bytes(holder.code, PNG, filename="local.png")
    note_here = await task_file_attach_bytes(holder.code, b"note bytes", filename="n.txt")
    assert here.file_code != rich.task_file and note_here.file_code != rich.note_file
    files_before = await _stored_count()

    plan, report = await run_import(path, workspace)

    context = (await task_crud.task_get(rich.root)).context
    assert f"FILE@{note_here.file_code}" in context and f"FILE@{rich.note_file}" not in context

    assert not any(c.id.startswith("FILE@") for c in plan.conflicts)
    assert {"entity": "file", "title": "Скриншот", "from": f"FILE@{rich.task_file}",
            "to": f"FILE@{here.file_code}"} in plan.recoded
    # Of four files two lie here already: only the stage's and the shared one are stored anew.
    assert await _stored_count() == files_before + 2
    assert await _owners(here.file_code) == {task_owner(holder.code), task_owner(rich.root)}
    bindings = await transfer_crud.bindings_of([rich.root])
    assert (rich.root, here.file_code) in bindings and (rich.root, rich.task_file) not in bindings
    context = (await task_crud.task_get(rich.root)).context
    assert f"IMAGE@{here.file_code}" in context and f"IMAGE@{rich.task_file}" not in context
    assert {"entity": "file", "title": "Скриншот", "from": f"FILE@{rich.task_file}",
            "to": f"FILE@{here.file_code}"} in report.recoded


async def test_a_reimport_takes_no_bytes_and_writes_only_bindings(rich, tmp_path):
    exported = await export_task(rich.root, tmp_path / "a.utsk")
    files_before = await _stored_count()
    owners_before = await _owners(rich.shared_file)

    plan = await analyze_archive(exported.path, workspace_code=rich.workspace)
    _, report = await import_archive(exported.path, workspace_code=rich.workspace, group_code=None,
                                     decisions=_all(plan, "replace"), plan_token=plan.token)

    assert await _stored_count() == files_before
    moved = {row["from"]: row["to"].split("@")[1] for row in report.recoded}
    copy_root, copy_child = moved[f"TASK@{rich.root}"], moved[f"TASK@{rich.child}"]
    assert await _owners(rich.shared_file) == owners_before | {task_owner(copy_root), task_owner(copy_child)}
    assert not any(row["from"].startswith("FILE@") for row in report.recoded)


async def test_a_soft_deleted_file_with_the_same_bytes_is_revived(rich, tmp_path, other_installation):
    path, workspace = await _carried(rich, tmp_path, other_installation)
    holder = await task_crud.task_create(workspace_code=workspace, title="Здешняя")
    binned = await task_file_attach_bytes(holder.code, b"note bytes", filename="x.txt")
    await file_delete(binned.file_code)

    await run_import(path, workspace)

    stored = await file_get(binned.file_code)
    assert stored.deleted_at is None
    assert task_owner(rich.root) in await _owners(binned.file_code)


async def test_bytes_a_codex_record_holds_are_shared_with_the_task(rich, tmp_path, other_installation, monkeypatch):
    from src.modules.codex.crud import codex as codex_crud
    from src.modules.codex.crud import note as codex_note_crud
    from src.modules.codex.file_owner import note_owner

    from ...codex.file_support import codex_file_attach_bytes

    path, workspace = await _carried(rich, tmp_path, other_installation)
    codex = await codex_crud.codex_create(segment="kb", title="База")
    record = (await codex_note_crud.note_create(parent_code=codex.code, segment="r", title="Запись")).code
    held = await codex_file_attach_bytes(record, PNG, filename="kb.png")

    # A failed import leaves the record's file as it was.
    async def broken(*_args, **_kwargs):
        raise RuntimeError("the rows failed")

    real_write = apply_module._write_rows
    monkeypatch.setattr(apply_module, "_write_rows", broken)
    plan = await analyze_archive(path, workspace_code=workspace)
    with pytest.raises(RuntimeError):
        await import_archive(path, workspace_code=workspace, group_code=None, decisions={}, plan_token=plan.token)
    assert await _owners(held.file_code) == {note_owner(record)}
    # Only this patch goes back: the storage and the transfer folder stay the test's own.
    monkeypatch.setattr(apply_module, "_write_rows", real_write)

    await run_import(path, workspace)

    assert await _owners(held.file_code) == {note_owner(record), task_owner(rich.root)}
    assert f"IMAGE@{held.file_code}" in (await task_crud.task_get(rich.root)).context


# ── Places, names, metadata ────────────────────────────────────────────────────


async def test_a_copy_keeps_each_file_in_its_note_or_stage(rich, tmp_path):
    exported = await export_task(rich.root, tmp_path / "a.utsk")
    plan = await analyze_archive(exported.path, workspace_code=rich.workspace)

    _, report = await import_archive(exported.path, workspace_code=rich.workspace, group_code=None,
                                     decisions=_all(plan, "replace"), plan_token=plan.token)

    moved = {row["from"]: row["to"].split("@")[1] for row in report.recoded}
    copy = moved[f"TASK@{rich.root}"]
    bindings = await transfer_crud.bindings_of([copy])
    assert bindings[(copy, rich.note_file)].note_code == moved[f"NOTE@{rich.notes[0]}"]
    assert bindings[(copy, rich.stage_file)].stage_code == moved[f"STAGE@{rich.stages[0]}"]
    assert bindings[(copy, rich.task_file)].note_code is None and bindings[(copy, rich.task_file)].stage_code is None
    # The original's places are untouched.
    original = await transfer_crud.bindings_of([rich.root])
    assert original[(rich.root, rich.note_file)].note_code == rich.notes[0]


async def test_each_holder_keeps_the_name_and_title_it_gave(rich, tmp_path, other_installation):
    path, workspace = await _carried(rich, tmp_path, other_installation)

    await run_import(path, workspace)

    names = {p.owner: p.original_filename + p.original_extension for p in await file_owners(rich.note_file)}
    assert names[task_owner(rich.root)] == "a.txt"
    bindings = await transfer_crud.bindings_of([rich.root, rich.child])
    assert bindings[(rich.root, rich.task_file)].title == "Скриншот"
    assert bindings[(rich.child, rich.shared_file)].title == "Общий"
    assert bindings[(rich.root, rich.shared_file)].title == ""


async def test_update_brings_the_binding_back_to_the_archive(rich, tmp_path):
    exported = await export_task(rich.root, tmp_path / "a.utsk")
    await task_file_retitle(rich.root, rich.task_file, title="Переименовано здесь")
    plan = await analyze_archive(exported.path, workspace_code=rich.workspace)

    await import_archive(exported.path, workspace_code=rich.workspace, group_code=rich.group,
                         decisions=_all(plan, "update"), plan_token=plan.token)

    binding = (await transfer_crud.bindings_of([rich.root]))[(rich.root, rich.task_file)]
    assert binding.title == "Скриншот"


async def test_a_file_whose_note_was_deleted_travels_without_a_place(rich, tmp_path, other_installation):
    doomed = await note_crud.task_note_add(task_code=rich.root, title="Уйдёт")
    attached = await task_file_attach_bytes(rich.root, b"doomed note bytes", filename="d.txt",
                                            place=FilePlace(note_code=doomed.code))
    await note_delete(doomed.code)
    exported = await export_task(rich.root, tmp_path / "a.utsk")
    row = next(r for r in read_rows(exported.path, "rows/files.jsonl") if r["binding"]["file_code"] == attached.file_code)
    assert row["binding"]["note_code"] is None
    await other_installation()
    workspace = (await workspace_create(title="Там")).code

    await run_import(exported.path, workspace)

    binding = (await transfer_crud.bindings_of([rich.root]))[(rich.root, attached.file_code)]
    assert binding.note_code is None


async def test_a_file_the_file_manager_deleted_does_not_travel(rich, tmp_path):
    await file_delete(rich.stage_file)

    exported = await export_task(rich.root, tmp_path / "a.utsk")

    codes = {r["binding"]["file_code"] for r in read_rows(exported.path, "rows/files.jsonl")}
    assert rich.stage_file not in codes and rich.task_file in codes


async def test_a_copy_s_journal_points_at_the_copy_s_stage(rich, tmp_path):
    exported = await export_task(rich.root, tmp_path / "a.utsk")
    plan = await analyze_archive(exported.path, workspace_code=rich.workspace)

    _, report = await import_archive(exported.path, workspace_code=rich.workspace, group_code=None,
                                     decisions=_all(plan, "replace"), plan_token=plan.token)

    moved = {row["from"]: row["to"].split("@")[1] for row in report.recoded}
    copy, copy_stage = moved[f"TASK@{rich.root}"], moved[f"STAGE@{rich.stages[0]}"]
    entries = {row.title: row for row in await transfer_crud.journal_of([copy])}
    assert entries["Факт"].stage_code == copy_stage
    original = {row.title: row for row in await transfer_crud.journal_of([rich.root])}
    assert original["Факт"].stage_code == rich.stages[0]


async def test_update_keeps_a_file_only_here(rich, tmp_path):
    exported = await export_task(rich.root, tmp_path / "a.utsk")
    local = await task_file_attach_bytes(rich.root, b"only here", filename="local.txt", title="Только здесь")
    plan = await analyze_archive(exported.path, workspace_code=rich.workspace)

    await import_archive(exported.path, workspace_code=rich.workspace, group_code=rich.group,
                         decisions=_all(plan, "update"), plan_token=plan.token)

    bindings = await transfer_crud.bindings_of([rich.root])
    assert bindings[(rich.root, local.file_code)].title == "Только здесь"
    assert task_owner(rich.root) in await _owners(local.file_code)


async def test_a_code_holding_other_bytes_gets_the_archive_s_bytes_under_a_new_code(rich, tmp_path, other_installation):
    from src.modules.core_storage.services.files import file_path
    from src.modules.core_storage.services.registration import file_register_path

    path, workspace = await _carried(rich, tmp_path, other_installation)
    source = tmp_path / "other.bin"
    source.write_bytes(b"something else entirely")
    forced = await file_register_path(source, store="public", owner=Owner("X", "1"), preferred_code=rich.stage_file)

    _, report = await run_import(path, workspace)

    new_code = next(r["to"] for r in report.recoded if r["from"] == f"FILE@{rich.stage_file}").split("@")[1]
    assert file_path(await file_get(new_code)).read_bytes() == b"stage bytes"
    assert file_path(await file_get(forced.code)).read_bytes() == b"something else entirely"
    bindings = await transfer_crud.bindings_of([rich.root])
    assert (rich.root, new_code) in bindings and (rich.root, rich.stage_file) not in bindings
    assert bindings[(rich.root, new_code)].stage_code == rich.stages[0]
    assert await _owners(forced.code) == {Owner("X", "1")}


# ── Failures ───────────────────────────────────────────────────────────────────


async def test_a_failure_while_taking_files_gives_back_the_ones_taken(rich, tmp_path, other_installation, monkeypatch):
    path, workspace = await _carried(rich, tmp_path, other_installation)
    real = apply_module.take_file
    calls: list[str] = []

    async def third_fails(reader, verdict, *, owner, store):
        calls.append(verdict.archived.code)
        if len(calls) == 3:
            raise RuntimeError("the storage failed")
        return await real(reader, verdict, owner=owner, store=store)

    monkeypatch.setattr(apply_module, "take_file", third_fails)
    plan = await analyze_archive(path, workspace_code=workspace)

    with pytest.raises(RuntimeError):
        await import_archive(path, workspace_code=workspace, group_code=None, decisions={}, plan_token=plan.token)

    for code in calls[:2]:
        assert await _owners(code) == set()
    assert await task_crud.task_get(rich.root, include_deleted=True) is None


async def test_a_failed_update_keeps_the_owners_the_task_had(rich, tmp_path, monkeypatch):
    exported = await export_task(rich.root, tmp_path / "a.utsk")
    before = {code: await _owners(code) for code in (rich.task_file, rich.note_file, rich.stage_file, rich.shared_file)}
    bindings_before = set(await transfer_crud.bindings_of([rich.root, rich.child]))

    async def broken(*_args, **_kwargs):
        raise RuntimeError("the rows failed")

    monkeypatch.setattr(apply_module, "_write_rows", broken)
    plan = await analyze_archive(exported.path, workspace_code=rich.workspace)

    with pytest.raises(RuntimeError):
        await import_archive(exported.path, workspace_code=rich.workspace, group_code=rich.group,
                             decisions=_all(plan, "update"), plan_token=plan.token)

    assert {code: await _owners(code) for code in before} == before
    assert set(await transfer_crud.bindings_of([rich.root, rich.child])) == bindings_before


async def test_a_failed_replace_gives_back_only_what_it_took(rich, tmp_path, monkeypatch):
    exported = await export_task(rich.root, tmp_path / "a.utsk")
    before = await _owners(rich.shared_file)

    async def broken(*_args, **_kwargs):
        raise RuntimeError("the rows failed")

    monkeypatch.setattr(apply_module, "_write_rows", broken)
    plan = await analyze_archive(exported.path, workspace_code=rich.workspace)

    with pytest.raises(RuntimeError):
        await import_archive(exported.path, workspace_code=rich.workspace, group_code=None,
                             decisions=_all(plan, "replace"), plan_token=plan.token)

    assert await _owners(rich.shared_file) == before


async def test_a_file_over_this_storage_ceiling_refuses_the_whole_import(rich, tmp_path, other_installation, monkeypatch):
    path, workspace = await _carried(rich, tmp_path, other_installation)

    class Small:
        max_file_size_mb = 0

    monkeypatch.setattr(storage_settings, "_current", Small())
    files_before = await _stored_count()

    with pytest.raises(TransferError) as caught:
        await analyze_archive(path, workspace_code=workspace)

    # The refusal names the file in the person's words, not the archive's entry.
    assert caught.value.code == errors.FILE_TOO_LARGE
    assert caught.value.params["name"] in {"shot.png", "a.txt", "b.txt", "c.txt"}
    assert await _stored_count() == files_before
    assert await task_crud.task_get(rich.root, include_deleted=True) is None


async def test_the_ceiling_holds_to_the_byte(rich, tmp_path, other_installation, monkeypatch):
    from src.modules.core_transfer import files as transfer_files

    path, workspace = await _carried(rich, tmp_path, other_installation)
    largest = max(len(PNG), len(b"note bytes"), len(b"stage bytes"), len(b"shared bytes"))

    monkeypatch.setattr(transfer_files, "max_file_size", lambda: largest)
    await analyze_archive(path, workspace_code=workspace)

    monkeypatch.setattr(transfer_files, "max_file_size", lambda: largest - 1)
    with pytest.raises(TransferError) as caught:
        await analyze_archive(path, workspace_code=workspace)
    assert caught.value.params["name"] == "shot.png"


async def test_a_file_whose_bytes_are_here_is_not_held_to_the_ceiling(rich, tmp_path, other_installation, monkeypatch):
    from src.modules.core_transfer import files as transfer_files

    path, workspace = await _carried(rich, tmp_path, other_installation)
    holder = await task_crud.task_create(workspace_code=workspace, title="Здешняя")
    await task_file_attach_bytes(holder.code, PNG, filename="local.png")
    # Only the picture is over the ceiling, and its bytes are here: nothing will be stored for it.
    monkeypatch.setattr(transfer_files, "max_file_size", lambda: len(PNG) - 1)

    plan, _ = await run_import(path, workspace)

    assert plan.conflicts == []
    assert task_owner(rich.root) in await _owners(next(iter(await _files_of(holder.code))))


async def _files_of(task_code: str) -> list[str]:
    return [file_code for (_, file_code) in await transfer_crud.bindings_of([task_code])]


# ── Crafted archives ───────────────────────────────────────────────────────────


async def test_a_row_claiming_the_sum_of_a_file_here_takes_nothing(rich, tmp_path, other_installation):
    path, workspace = await _carried(rich, tmp_path, other_installation)
    # A private file of this installation the archive does not carry.
    victim_task = await task_crud.task_create(workspace_code=workspace, title="Чужое")
    victim = await task_file_attach_bytes(victim_task.code, b"secret bytes here", filename="secret.txt")
    rows = read_rows(path, "rows/files.jsonl")
    for row in rows:
        if row["binding"]["file_code"] == rich.note_file:
            row["stored"]["sha256"] = hashlib.sha256(b"secret bytes here").hexdigest()
            row["stored"]["size"] = len(b"secret bytes here")
    crafted = rewrite_archive(path, tmp_path / "crafted.utsk", {"rows/files.jsonl": jsonl(rows)})

    with pytest.raises(TransferError) as caught:
        await analyze_archive(crafted, workspace_code=workspace)

    assert caught.value.code == errors.ARCHIVE_INCONSISTENT
    assert await _owners(victim.file_code) == {task_owner(victim_task.code)}


async def test_one_content_under_two_codes_is_refused(rich, tmp_path, other_installation):
    path, workspace = await _carried(rich, tmp_path, other_installation)
    rows = read_rows(path, "rows/files.jsonl")
    note_row = next(r for r in rows if r["binding"]["file_code"] == rich.note_file)
    stage_row = next(r for r in rows if r["binding"]["file_code"] == rich.stage_file)
    stage_row["stored"]["sha256"] = note_row["stored"]["sha256"]
    crafted = rewrite_archive(path, tmp_path / "crafted.utsk", {"rows/files.jsonl": jsonl(rows)})

    with pytest.raises(TransferError) as caught:
        await analyze_archive(crafted, workspace_code=workspace)

    assert caught.value.code == errors.ARCHIVE_INCONSISTENT


async def test_one_content_under_two_codes_is_refused_by_that_check(rich, tmp_path, other_installation):
    path, workspace = await _carried(rich, tmp_path, other_installation)
    rows = read_rows(path, "rows/files.jsonl")
    note_row = next(r for r in rows if r["binding"]["file_code"] == rich.note_file)
    stage_row = next(r for r in rows if r["binding"]["file_code"] == rich.stage_file)
    # The stage's entry carries the note's very bytes: each row's sum matches its own bytes, so only
    # the «one content, two codes» check can refuse.
    stage_row["stored"]["sha256"] = note_row["stored"]["sha256"]
    stage_row["stored"]["size"] = note_row["stored"]["size"]
    crafted = rewrite_archive(path, tmp_path / "crafted.utsk", {
        "rows/files.jsonl": jsonl(rows), stage_row["entry"]: b"note bytes",
    })

    with pytest.raises(TransferError) as caught:
        await analyze_archive(crafted, workspace_code=workspace)

    assert caught.value.code == errors.ARCHIVE_INCONSISTENT
    assert "two codes" in str(caught.value)


async def test_a_note_body_larger_than_any_body_written_is_refused_unread(rich, tmp_path, other_installation):
    path, workspace = await _carried(rich, tmp_path, other_installation)
    oversized = b"x" * (4 * 65536 + 1)
    crafted = rewrite_archive(path, tmp_path / "crafted.utsk", {f"bodies/notes/{rich.notes[0]}.md": oversized})

    with pytest.raises(TransferError) as caught:
        await analyze_archive(crafted, workspace_code=workspace)

    assert caught.value.code == errors.ARCHIVE_INCONSISTENT
    assert await task_crud.task_get(rich.root, include_deleted=True) is None


async def test_a_file_row_without_its_bytes_is_refused(rich, tmp_path, other_installation):
    path, workspace = await _carried(rich, tmp_path, other_installation)
    rows = read_rows(path, "rows/files.jsonl")
    rows[0]["entry"] = "files/0000000000.png"
    crafted = rewrite_archive(path, tmp_path / "crafted.utsk", {"rows/files.jsonl": jsonl(rows)})

    with pytest.raises(TransferError) as caught:
        await analyze_archive(crafted, workspace_code=workspace)

    assert caught.value.code == errors.ARCHIVE_INCONSISTENT
