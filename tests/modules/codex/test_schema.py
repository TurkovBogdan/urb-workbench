"""What the ``codex`` schema holds by itself, before any service stands in front of it.

Each refusal is checked next to its positive control: the same insert with one thing changed goes
through, so a red test points at the rule and not at a broken fixture.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from sqlalchemy import delete, func, select
from sqlalchemy.exc import IntegrityError

from src.core.database import session_scope, write_scope
from src.modules.codex.crud.code import codex_new_code
from src.modules.codex.models import Codex, CodexMount, CodexNote
from src.modules.workspace.models import Workspace

pytestmark = pytest.mark.db


async def _add(*rows) -> None:
    async with write_scope() as s:
        s.add_all(rows)
        await s.flush()


async def _count(model) -> int:
    async with session_scope() as s:
        return await s.scalar(select(func.count()).select_from(model))


def _codex(code: str = "C000000001", slug: str = "python", **kw) -> Codex:
    return Codex(code=code, slug=slug, title=slug.capitalize(), **kw)


def _note(code: str, slug: str, *, parent: str | None = None, codex: str = "C000000001", **kw):
    return CodexNote(
        code=code, codex_code=codex, parent_code=parent, slug=slug, title=slug, **kw
    )


@pytest.fixture
async def python(db):
    await _add(_codex(), _note("N000000001", "test"))


# ── codex slug ────────────────────────────────────────────────────────────────


async def test_two_live_codexes_cannot_share_a_slug(db):
    await _add(_codex())

    with pytest.raises(IntegrityError, match="UNIQUE"):
        await _add(_codex("C000000002", "python"))
    await _add(_codex("C000000002", "vue"))


async def test_a_deleted_codex_frees_its_slug(db):
    await _add(_codex(deleted_at=datetime.now(UTC)))

    await _add(_codex("C000000002", "python"))
    assert await _count(Codex) == 2


# ── note slug among siblings ──────────────────────────────────────────────────


async def test_two_top_level_notes_of_one_codex_cannot_share_a_slug(python):
    with pytest.raises(IntegrityError, match="UNIQUE"):
        await _add(_note("N000000002", "test"))
    await _add(_note("N000000002", "lint"))


async def test_the_same_top_slug_in_another_codex_is_fine(python):
    await _add(_codex("C000000002", "vue"), _note("N000000002", "test", codex="C000000002"))

    assert await _count(CodexNote) == 2


async def test_two_children_of_one_parent_cannot_share_a_slug(python):
    await _add(_note("N000000002", "fixtures", parent="N000000001"))

    with pytest.raises(IntegrityError, match="UNIQUE"):
        await _add(_note("N000000003", "fixtures", parent="N000000001"))
    await _add(_note("N000000003", "factories", parent="N000000001"))


async def test_a_child_may_repeat_a_top_level_slug(python):
    """The top-level index and the child index are separate namespaces per level."""
    await _add(_note("N000000002", "test", parent="N000000001"))

    assert await _count(CodexNote) == 2


async def test_a_deleted_note_frees_its_slug(python):
    await _add(
        _note("N000000002", "fixtures", parent="N000000001", deleted_at=datetime.now(UTC))
    )

    await _add(_note("N000000003", "fixtures", parent="N000000001"))
    assert await _count(CodexNote) == 3


# ── the tree ──────────────────────────────────────────────────────────────────


async def test_a_note_cannot_be_its_own_parent(python):
    with pytest.raises(IntegrityError, match="ck_codex_note_not_own_parent|CHECK"):
        await _add(_note("N000000002", "loop", parent="N000000002"))


async def test_a_parent_must_exist(python):
    with pytest.raises(IntegrityError, match="FOREIGN KEY"):
        await _add(_note("N000000002", "orphan", parent="N00000000F"))


async def test_a_hard_deleted_codex_takes_its_tree_and_mounts(python, workspace):
    await _add(
        _note("N000000002", "fixtures", parent="N000000001"),
        CodexMount(codex_code="C000000001", workspace_code=workspace.code),
    )

    async with write_scope() as s:
        await s.execute(delete(Codex).where(Codex.code == "C000000001"))

    assert (await _count(CodexNote), await _count(CodexMount)) == (0, 0)


async def test_a_hard_deleted_note_takes_its_branch_only(python):
    await _add(
        _note("N000000002", "fixtures", parent="N000000001"),
        _note("N000000003", "lint"),
    )

    async with write_scope() as s:
        await s.execute(delete(CodexNote).where(CodexNote.code == "N000000001"))

    async with session_scope() as s:
        left = (await s.scalars(select(CodexNote.code))).all()
    assert left == ["N000000003"]


# ── the mount ─────────────────────────────────────────────────────────────────


async def test_a_mount_lets_the_agent_edit_by_default(python, workspace):
    await _add(CodexMount(codex_code="C000000001", workspace_code=workspace.code))

    async with session_scope() as s:
        mount = await s.scalar(select(CodexMount))
    assert (mount.agent_can_edit, mount.sort) == (True, 500)


async def test_a_codex_is_mounted_into_a_workspace_once(python, workspace):
    await _add(CodexMount(codex_code="C000000001", workspace_code=workspace.code))

    with pytest.raises(IntegrityError, match="UNIQUE"):
        await _add(CodexMount(codex_code="C000000001", workspace_code=workspace.code))


async def test_a_hard_deleted_workspace_takes_its_mounts(python, workspace):
    await _add(CodexMount(codex_code="C000000001", workspace_code=workspace.code))

    async with write_scope() as s:
        await s.execute(delete(Workspace).where(Workspace.code == workspace.code))

    assert (await _count(CodexMount), await _count(Codex)) == (0, 1)


# ── one code space over two tables ────────────────────────────────────────────


async def test_a_fresh_code_skips_codes_taken_in_either_table(python, monkeypatch):
    draws = iter(["C000000001", "N000000001", "F000000001"])
    monkeypatch.setattr("src.modules.codex.crud.code.new_code", lambda: next(draws))

    async with write_scope() as s:
        assert await codex_new_code(s) == "F000000001"


async def test_a_generator_that_never_finds_a_free_code_fails_loudly(python, monkeypatch):
    monkeypatch.setattr("src.modules.codex.crud.code.new_code", lambda: "N000000001")

    async with write_scope() as s:
        with pytest.raises(RuntimeError, match="No free CODEX@ code"):
            await codex_new_code(s)
