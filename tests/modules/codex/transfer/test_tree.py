"""The codex tree through a transfer: the bin deeper than four levels, a branch the archive bins,
and a mix of choices that would break the levels — each checked by the tree left behind."""

from __future__ import annotations

import shutil

import pytest

from src.modules.codex.crud import codex as codex_crud
from src.modules.codex.crud import note as note_crud
from src.modules.codex.file_owner import note_owner
from src.modules.codex.transfer.collect import export_codex
from src.modules.codex.transfer.runner import analyze_archive, import_archive
from src.modules.core_storage.services.ownership import file_owners
from src.modules.core_transfer import errors
from src.modules.core_transfer.errors import TransferError

from ..file_support import codex_file_attach_bytes

pytestmark = pytest.mark.db


async def _note(code: str):
    return await note_crud.note_get(code, include_deleted=True)


async def test_a_bin_deeper_than_four_levels_travels(db, tmp_path, other_installation):
    codex = (await codex_crud.codex_create(segment="deep", title="Глубокая")).code
    other_top = (await note_crud.note_create(parent_code=codex, segment="x", title="X")).code
    a = (await note_crud.note_create(parent_code=codex, segment="a", title="A")).code
    b = (await note_crud.note_create(parent_code=a, segment="b", title="B")).code
    c = (await note_crud.note_create(parent_code=b, segment="c", title="C")).code
    await note_crud.note_delete(c)
    # The service counts only the live height: the deleted C rides along to the fifth level.
    await note_crud.note_update(a, parent_code=other_top)
    exported = await export_codex(codex, tmp_path / "a.ucdx")
    kept = tmp_path / "kept.ucdx"
    shutil.copy(exported.path, kept)
    await other_installation()

    plan = await analyze_archive(kept)
    await import_archive(kept, workspace_code=None, decisions={}, plan_token=plan.token)

    moved = await _note(c)
    assert moved is not None and moved.deleted_at is not None and moved.parent_code == b
    assert (await _note(a)).parent_code == other_top


async def test_a_record_the_archive_bins_takes_its_live_branch_here_along(db, tmp_path):
    codex = (await codex_crud.codex_create(segment="bin", title="Корзина")).code
    parent = (await note_crud.note_create(parent_code=codex, segment="p", title="P")).code
    await note_crud.note_delete(parent)
    exported = await export_codex(codex, tmp_path / "a.ucdx")
    await note_crud.note_restore(parent)
    child = (await note_crud.note_create(parent_code=parent, segment="y", title="Y")).code
    grandchild = (await note_crud.note_create(parent_code=child, segment="z", title="Z")).code
    plan = await analyze_archive(exported.path)

    _, report = await import_archive(exported.path, workspace_code=None,
                                     decisions={c.id: "update" for c in plan.conflicts}, plan_token=plan.token)

    binned_parent = await _note(parent)
    assert binned_parent.deleted_at is not None
    # The branch went with the same mark: one restore brings it all back.
    assert (await _note(child)).deleted_at == binned_parent.deleted_at
    assert (await _note(grandchild)).deleted_at == binned_parent.deleted_at
    assert {row["code"] for row in report.binned} == {f"CODEX@{child}", f"CODEX@{grandchild}"}
    assert await note_crud.note_restore(parent)
    assert (await _note(grandchild)).deleted_at is None


async def test_a_mix_of_choices_that_breaks_the_levels_is_refused_by_its_own_reason(db, tmp_path):
    codex = (await codex_crud.codex_create(segment="mix", title="Смесь")).code
    a = (await note_crud.note_create(parent_code=codex, segment="a", title="A")).code
    p = (await note_crud.note_create(parent_code=a, segment="p", title="P")).code
    leaf = (await note_crud.note_create(parent_code=codex, segment="l", title="L")).code
    # L's file: its «replace» copy takes the file before the rows are written, so the refusal from
    # inside the write must give that owner back.
    attached = await codex_file_attach_bytes(leaf, b"tree file", filename="t.txt")
    exported = await export_codex(codex, tmp_path / "a.ucdx")
    # Here the tree went another way: P on top, L under P, and M only here under L.
    await note_crud.note_update(p, parent_code=codex)
    await note_crud.note_update(leaf, parent_code=p)
    only_here = (await note_crud.note_create(parent_code=leaf, segment="m", title="M")).code
    plan = await analyze_archive(exported.path)
    assert all("update" in c.options for c in plan.conflicts)
    decisions = {c.id: "update" for c in plan.conflicts} | {f"CODEX@{leaf}": "replace"}

    with pytest.raises(TransferError) as caught:
        await import_archive(exported.path, workspace_code=None, decisions=decisions, plan_token=plan.token)

    assert caught.value.code == errors.DEPTH_EXCEEDED
    assert caught.value.params["record"] == f"CODEX@{only_here}"
    # Nothing moved: the tree is the one here, and the file has only the owner it had.
    assert (await _note(p)).parent_code is None
    assert (await _note(leaf)).parent_code == p
    assert {place.owner for place in await file_owners(attached.file_code)} == {note_owner(leaf)}

    # With every record updated the same archive goes in.
    await import_archive(exported.path, workspace_code=None,
                         decisions={c.id: "update" for c in plan.conflicts}, plan_token=plan.token)
    assert (await _note(p)).parent_code == a
    assert (await _note(leaf)).parent_code is None
    assert (await _note(only_here)).parent_code == leaf
