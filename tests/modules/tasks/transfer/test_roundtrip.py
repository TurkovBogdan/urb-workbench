"""Export → import into another installation: the task «with everything» comes back the same.

Every row is compared column by column, except what an import is meant to change — the workspace,
the group, ``updated_at``. Codes stay, files keep their ``FILE@`` and their bytes.
"""

from __future__ import annotations

import shutil

import pytest
from sqlalchemy import update

from src.core.database import write_scope
from src.modules.core_storage.services.files import file_get, file_path
from src.modules.core_storage.services.ownership import file_owners
from src.modules.tasks.crud import group as group_crud
from src.modules.tasks.crud import transfer as transfer_crud
from src.modules.tasks.crud.task import task_get
from src.modules.tasks.file_owner import task_owner
from src.modules.tasks.models.link import TasksLink
from src.modules.tasks.models.note import TasksNote
from src.modules.tasks.transfer.collect import export_task
from src.modules.workspace.crud.workspace import workspace_create

from .support import run_import, snapshot

pytestmark = pytest.mark.db


async def _carried(rich, tmp_path, other_installation):
    """The archive of ``rich``, its snapshot, and a fresh installation with a workspace and group."""
    exported = await export_task(rich.root, tmp_path / "a.utsk")
    kept = tmp_path / "carried.utsk"
    shutil.copy(exported.path, kept)
    before = await snapshot([rich.root, rich.child])
    bytes_before = {code: file_path(await file_get(code)).read_bytes()
                    for code in (rich.task_file, rich.note_file, rich.stage_file, rich.shared_file)}
    await other_installation()
    workspace = (await workspace_create(title="Другое место")).code
    group = (await group_crud.group_create(workspace_code=workspace, title="Сюда")).code
    return kept, before, bytes_before, workspace, group


async def test_every_row_comes_back_with_its_code(rich, tmp_path, other_installation):
    path, before, _, workspace, group = await _carried(rich, tmp_path, other_installation)

    plan, report = await run_import(path, workspace, group=group)

    assert plan.conflicts == []
    assert report.task_code == rich.root
    assert report.recoded == []
    assert report.refs_rewritten == 0
    after = await snapshot([rich.root, rich.child])
    assert after == before


async def test_the_root_lands_in_the_chosen_group_and_the_subtask_follows(rich, tmp_path, other_installation):
    path, _, _, workspace, group = await _carried(rich, tmp_path, other_installation)

    await run_import(path, workspace, group=group)

    root, child = await task_get(rich.root), await task_get(rich.child)
    links = await transfer_crud.links_of([rich.root, rich.child])
    assert (root.workspace_code, root.group_code) == (workspace, group)
    assert (child.workspace_code, child.group_code) == (workspace, group)
    assert links[rich.root].parent_code is None
    assert links[rich.child].parent_code == rich.root


@pytest.mark.parametrize("position", [0, -10])
async def test_a_position_at_zero_or_below_keeps_its_place(rich, tmp_path, other_installation, position):
    # A row reordered by hand lands at 0 and below; zero is a place, not a missing value.
    async with write_scope() as s:
        await s.execute(update(TasksLink).where(TasksLink.task_code == rich.child).values(sort=position))
        await s.execute(update(TasksNote).where(TasksNote.note_code == rich.notes[0]).values(sort=position))
    path, before, _, workspace, _ = await _carried(rich, tmp_path, other_installation)

    await run_import(path, workspace)

    assert (await transfer_crud.links_of([rich.child]))[rich.child].sort == position
    assert (await snapshot([rich.root, rich.child])) == before


async def test_without_a_group_the_task_lands_in_no_group(rich, tmp_path, other_installation):
    path, _, _, workspace, _ = await _carried(rich, tmp_path, other_installation)

    await run_import(path, workspace)

    assert (await task_get(rich.root)).group_code is None
    assert (await task_get(rich.child)).group_code is None


async def test_files_keep_their_codes_bytes_and_owners(rich, tmp_path, other_installation):
    path, _, bytes_before, workspace, _ = await _carried(rich, tmp_path, other_installation)

    await run_import(path, workspace)

    for code, payload in bytes_before.items():
        assert file_path(await file_get(code)).read_bytes() == payload
    shared = {place.owner for place in await file_owners(rich.shared_file)}
    assert shared == {task_owner(rich.root), task_owner(rich.child)}
    names = {place.owner: place.original_filename + place.original_extension
             for place in await file_owners(rich.task_file)}
    assert names[task_owner(rich.root)] == "shot.png"


async def test_deleted_things_did_not_travel(rich, tmp_path, other_installation):
    path, _, _, workspace, _ = await _carried(rich, tmp_path, other_installation)

    await run_import(path, workspace)

    assert await task_get(rich.deleted_child, include_deleted=True) is None
    assert rich.deleted_note not in await transfer_crud.notes_by_codes([rich.deleted_note])


async def test_a_subtask_exported_alone_becomes_a_top_level_task(rich, tmp_path, other_installation):
    exported = await export_task(rich.child, tmp_path / "a.utsk")
    await other_installation()
    workspace = (await workspace_create(title="Другое место")).code

    await run_import(exported.path, workspace)

    links = await transfer_crud.links_of([rich.child])
    assert links[rich.child].parent_code is None
    assert (await task_get(rich.child)).workspace_code == workspace
