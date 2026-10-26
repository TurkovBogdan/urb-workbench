"""A task archive brought back where its codes are taken: conflicts, «update», «replace», and
what a refusal leaves — checked by the rows, not by the answer."""

from __future__ import annotations

import pytest
from sqlalchemy import func, select

from src.core.database import session_scope
from src.modules.core_storage.services.files import file_get
from src.modules.core_storage.services.ownership import file_owners
from src.modules.core_storage.services.registration import file_register_bytes
from src.modules.core_storage.dto import Owner
from src.modules.core_transfer import errors
from src.modules.core_transfer.errors import TransferError
from src.modules.notes.crud.note import note_get
from src.modules.tasks.crud import note as note_crud
from src.modules.tasks.crud import stage as stage_crud
from src.modules.tasks.crud import task as task_crud
from src.modules.tasks.crud import transfer as transfer_crud
from src.modules.tasks.file_owner import task_owner
from src.modules.tasks.models.task import TasksTask
from src.modules.tasks.transfer import apply as apply_module
from src.modules.tasks.transfer.collect import export_task
from src.modules.tasks.transfer.runner import analyze_archive, import_archive
from src.modules.workspace.crud.workspace import workspace_create

from .support import run_import

pytestmark = pytest.mark.db


async def _task_count() -> int:
    async with session_scope() as s:
        return (await s.execute(select(func.count()).select_from(TasksTask))).scalar_one()


def _all(plan, choice: str) -> dict[str, str]:
    return {c.id: choice for c in plan.conflicts if choice in c.options}


async def test_a_reimport_names_every_taken_task_and_note(rich, tmp_path):
    exported = await export_task(rich.root, tmp_path / "a.utsk")

    plan = await analyze_archive(exported.path, workspace_code=rich.workspace)

    by_id = {c.id: c for c in plan.conflicts}
    assert set(by_id) == {
        f"TASK@{rich.root}", f"TASK@{rich.child}",
        *(f"NOTE@{code}" for code in (*rich.notes, rich.child_note)),
    }
    assert by_id[f"TASK@{rich.root}"].options == ("update", "replace")
    assert by_id[f"TASK@{rich.child}"].requires == (f"TASK@{rich.root}", "update")
    assert by_id[f"NOTE@{rich.child_note}"].requires == (f"TASK@{rich.child}", "update")
    # The same bytes under the same code are not a conflict.
    assert not any(c.id.startswith("FILE@") for c in plan.conflicts)
    # Both sides carry their dates.
    dates = by_id[f"TASK@{rich.root}"].as_dict()["dates"]
    assert dates["local"]["updated_at"] and dates["archive"]["updated_at"]


async def test_update_writes_the_archive_over_and_keeps_what_is_only_here(rich, tmp_path):
    exported = await export_task(rich.root, tmp_path / "a.utsk")
    await task_crud.task_update(rich.root, title="Правлено здесь")
    extra_stage = await stage_crud.stage_create(task_code=rich.root, title="Только здесь")
    extra_note = await note_crud.task_note_add(task_code=rich.root, title="Местная заметка")
    count = await _task_count()

    plan = await analyze_archive(exported.path, workspace_code=rich.workspace)
    _, report = await import_archive(exported.path, workspace_code=rich.workspace, group_code=rich.group,
                                     decisions=_all(plan, "update"), plan_token=plan.token)

    assert await _task_count() == count
    assert (await task_crud.task_get(rich.root)).title == "Перенос задачи"
    assert await stage_crud.stage_get(extra_stage.code) is not None
    assert await note_get(extra_note.code) is not None
    assert report.recoded == []
    assert report.updated["tasks"] == 2 and report.created["tasks"] == 0


async def test_replace_makes_a_copy_and_moves_the_references(rich, tmp_path):
    exported = await export_task(rich.root, tmp_path / "a.utsk")
    count = await _task_count()

    plan = await analyze_archive(exported.path, workspace_code=rich.workspace)
    _, report = await import_archive(exported.path, workspace_code=rich.workspace, group_code=None,
                                     decisions=_all(plan, "replace"), plan_token=plan.token)

    assert await _task_count() == count + 2
    moved = {row["from"]: row["to"] for row in report.recoded}
    copy = moved[f"TASK@{rich.root}"].split("@")[1]
    child_copy = moved[f"TASK@{rich.child}"]
    note_copy = moved[f"NOTE@{rich.notes[0]}"]
    stage_copy = moved[f"STAGE@{rich.stages[0]}"]
    entry_copy = moved[f"JOURNAL@{rich.entries[0]}"]
    context = (await task_crud.task_get(copy)).context
    assert note_copy in context and stage_copy in context and entry_copy in context and child_copy in context
    # A file of the same bytes is the same file: the copy holds it under the same code.
    assert f"IMAGE@{rich.task_file}" in context
    assert f"TASK@{rich.outside}" in context
    assert task_owner(copy) in {place.owner for place in await file_owners(rich.task_file)}
    # The original is untouched.
    assert (await task_crud.task_get(rich.root)).context.count(f"NOTE@{rich.notes[0]}") == 1
    note_body = (await note_get(note_copy.split("@")[1])).body
    assert f"TASK@{copy}" in note_body and moved[f"STAGE@{rich.stages[1]}"] in note_body


async def test_a_note_cannot_be_updated_without_its_task(rich, tmp_path):
    exported = await export_task(rich.root, tmp_path / "a.utsk")
    plan = await analyze_archive(exported.path, workspace_code=rich.workspace)
    decisions = _all(plan, "replace") | {f"NOTE@{rich.notes[0]}": "update"}
    count = await _task_count()

    with pytest.raises(TransferError) as caught:
        await import_archive(exported.path, workspace_code=rich.workspace, group_code=None,
                             decisions=decisions, plan_token=plan.token)

    assert caught.value.code == errors.DECISION_INVALID
    assert await _task_count() == count


async def test_every_conflict_needs_a_choice(rich, tmp_path):
    exported = await export_task(rich.root, tmp_path / "a.utsk")
    plan = await analyze_archive(exported.path, workspace_code=rich.workspace)

    with pytest.raises(TransferError) as caught:
        await import_archive(exported.path, workspace_code=rich.workspace, group_code=None,
                             decisions={}, plan_token=plan.token)

    assert caught.value.code == errors.DECISION_INVALID


async def test_another_workspace_offers_replace_only(rich, tmp_path):
    exported = await export_task(rich.root, tmp_path / "a.utsk")
    elsewhere = (await workspace_create(title="Другое")).code

    plan = await analyze_archive(exported.path, workspace_code=elsewhere)
    root = next(c for c in plan.conflicts if c.id == f"TASK@{rich.root}")
    note = next(c for c in plan.conflicts if c.id == f"NOTE@{rich.notes[0]}")

    assert root.options == ("replace",) and root.reason == "task_other_workspace"
    assert root.reason_params == {"workspace": "Работа"}
    assert note.options == ("replace",) and note.reason == "note_other_task"

    _, report = await import_archive(exported.path, workspace_code=elsewhere, group_code=None,
                                     decisions={}, plan_token=plan.token)
    copy = await task_crud.task_get(report.task_code)
    assert copy.workspace_code == elsewhere and report.task_code != rich.root
    assert (await task_crud.task_get(rich.root)).workspace_code == rich.workspace


async def test_a_subtask_only_here_follows_the_root_into_the_new_group(rich, tmp_path):
    exported = await export_task(rich.root, tmp_path / "a.utsk")
    local_child = await task_crud.task_create(workspace_code=rich.workspace, parent_code=rich.root, title="Только здесь")
    from src.modules.tasks.crud import group as group_crud

    target = (await group_crud.group_create(workspace_code=rich.workspace, title="Новая")).code
    plan = await analyze_archive(exported.path, workspace_code=rich.workspace)

    await import_archive(exported.path, workspace_code=rich.workspace, group_code=target,
                         decisions=_all(plan, "update"), plan_token=plan.token)

    assert (await task_crud.task_get(rich.root)).group_code == target
    assert (await task_crud.task_get(rich.child)).group_code == target
    assert (await task_crud.task_get(local_child.code)).group_code == target


async def test_a_deleted_task_is_brought_back_by_update(rich, tmp_path):
    exported = await export_task(rich.root, tmp_path / "a.utsk")
    await task_crud.task_delete(rich.root)

    plan = await analyze_archive(exported.path, workspace_code=rich.workspace)
    await import_archive(exported.path, workspace_code=rich.workspace, group_code=rich.group,
                         decisions=_all(plan, "update"), plan_token=plan.token)

    assert (await task_crud.task_get(rich.root)) is not None
    assert (await task_crud.task_get(rich.child)) is not None


async def test_a_taken_stage_number_moves_to_the_next(rich, tmp_path):
    exported = await export_task(rich.root, tmp_path / "a.utsk")
    await stage_crud.stage_delete(rich.stages[1])
    squatter = await stage_crud.stage_create(task_code=rich.root, title="Занял номер", number=2)

    plan = await analyze_archive(exported.path, workspace_code=rich.workspace)
    _, report = await import_archive(exported.path, workspace_code=rich.workspace, group_code=rich.group,
                                     decisions=_all(plan, "update"), plan_token=plan.token)

    returned = await stage_crud.stage_get(rich.stages[1])
    assert returned is not None and returned.number == 3
    assert (await stage_crud.stage_get(squatter.code)).number == 2
    assert report.renumbered == [{"code": f"STAGE@{rich.stages[1]}", "title": "Второй этап", "from": 2, "to": 3}]


async def test_a_code_holding_other_bytes_brings_a_new_file(rich, tmp_path, other_installation):
    exported = await export_task(rich.root, tmp_path / "a.utsk")
    await other_installation()
    workspace = (await workspace_create(title="Другое место")).code
    squatter = await file_register_bytes(b"other bytes", store="public", owner=Owner("X", "1"),
                                         filename="x.bin")
    # The same code holding another content — only a collision would do it; force one.
    from src.modules.core_storage.services.registration import file_register_path

    source = tmp_path / "other.bin"
    source.write_bytes(b"something else")
    forced = await file_register_path(source, store="public", owner=Owner("X", "2"), preferred_code=rich.task_file)
    assert forced.code == rich.task_file and squatter.code != rich.task_file

    plan = await analyze_archive(exported.path, workspace_code=workspace)
    conflict = next(c for c in plan.conflicts if c.id == f"FILE@{rich.task_file}")
    assert conflict.options == ("replace",) and conflict.reason == "file_other_content"
    assert conflict.archive.size and conflict.here.size == len(b"something else")

    _, report = await import_archive(exported.path, workspace_code=workspace, group_code=None,
                                     decisions={}, plan_token=plan.token)

    new_code = next(row["to"] for row in report.recoded if row["from"] == f"FILE@{rich.task_file}")
    assert new_code != f"FILE@{rich.task_file}"
    context = (await task_crud.task_get(rich.root)).context
    assert f"IMAGE@{new_code.split('@')[1]}" in context
    assert (await file_get(rich.task_file)).sha256 == forced.sha256


async def test_a_changed_base_refuses_the_old_plan(rich, tmp_path, other_installation):
    exported = await export_task(rich.root, tmp_path / "a.utsk")
    await other_installation()
    workspace = (await workspace_create(title="Другое место")).code
    stale = await analyze_archive(exported.path, workspace_code=workspace)
    await run_import(exported.path, workspace)

    with pytest.raises(TransferError) as caught:
        await import_archive(exported.path, workspace_code=workspace, group_code=None,
                             decisions={}, plan_token=stale.token)

    assert caught.value.code == errors.PLAN_CHANGED


async def test_a_failure_in_the_rows_leaves_neither_rows_nor_owners(rich, tmp_path, other_installation, monkeypatch):
    exported = await export_task(rich.root, tmp_path / "a.utsk")
    await other_installation()
    workspace = (await workspace_create(title="Другое место")).code

    async def broken(*_args, **_kwargs):
        raise RuntimeError("the rows failed")

    monkeypatch.setattr(apply_module, "_write_rows", broken)
    plan = await analyze_archive(exported.path, workspace_code=workspace)

    with pytest.raises(RuntimeError):
        await import_archive(exported.path, workspace_code=workspace, group_code=None,
                             decisions={}, plan_token=plan.token)

    assert await task_crud.task_get(rich.root, include_deleted=True) is None
    for code in (rich.task_file, rich.note_file, rich.stage_file, rich.shared_file):
        assert await file_owners(code) == []
    assert await transfer_crud.bindings_of([rich.root]) == {}
