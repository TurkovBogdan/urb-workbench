"""The codex tree service: every rule refused next to the neighbouring case it allows, and the
data read back after each refusal.

The fixture tree, in the codex ``python``::

    test            (2)
      fixtures      (3)
        factories   (4)
    lint            (2)
"""

from __future__ import annotations

import pytest
from sqlalchemy import select

from src.core.database import session_scope
from src.modules.codex.crud.codex import codex_create, codex_delete
from src.modules.codex.crud.note import note_create, note_delete, note_get, note_restore, note_update
from src.modules.codex.models import CodexNote

pytestmark = pytest.mark.db


@pytest.fixture
async def tree(db):
    python = await codex_create(slug="python", title="Python")
    test = await note_create(parent_code=python.code, slug="test", title="Тесты")
    fixtures = await note_create(parent_code=test.code, slug="fixtures", title="Фикстуры")
    factories = await note_create(parent_code=fixtures.code, slug="factories", title="Фабрики")
    lint = await note_create(parent_code=python.code, slug="lint", title="Линтер")
    return {
        "python": python,
        "test": test,
        "fixtures": fixtures,
        "factories": factories,
        "lint": lint,
    }


async def _row(code: str) -> CodexNote:
    return await note_get(code, include_deleted=True)


async def _order(codex_code: str, parent_code: str | None) -> list[str]:
    stmt = (
        select(CodexNote.slug)
        .where(CodexNote.codex_code == codex_code, CodexNote.deleted_at.is_(None))
        .order_by(CodexNote.sort.desc(), CodexNote.code.asc())
    )
    stmt = stmt.where(
        CodexNote.parent_code.is_(None) if parent_code is None else CodexNote.parent_code == parent_code
    )
    async with session_scope() as s:
        return list((await s.scalars(stmt)).all())


# ── create ────────────────────────────────────────────────────────────────────


async def test_a_note_lands_under_its_parent_at_the_end_of_the_row(tree):
    assert tree["test"].parent_code is None
    assert tree["fixtures"].parent_code == tree["test"].code
    assert {n.codex_code for n in (tree["test"], tree["factories"])} == {tree["python"].code}
    assert await _order(tree["python"].code, None) == ["test", "lint"]


async def test_the_fourth_level_is_allowed_the_fifth_refused(tree):
    with pytest.raises(ValueError, match="reach 5 levels, the limit is 4"):
        await note_create(parent_code=tree["factories"].code, slug="deep", title="Глубже")

    assert await _order(tree["python"].code, tree["factories"].code) == []
    await note_create(parent_code=tree["fixtures"].code, slug="pytest", title="Pytest")


async def test_a_slug_taken_among_siblings_is_refused_naming_the_sibling(tree):
    with pytest.raises(ValueError, match=f"taken under the codex 'python' by the note 'Тесты' \\(CODEX@{tree['test'].code}\\)"):
        await note_create(parent_code=tree["python"].code, slug="test", title="Ещё")

    assert await _order(tree["python"].code, None) == ["test", "lint"]
    await note_create(parent_code=tree["lint"].code, slug="test", title="Тест линтера")


async def test_a_bad_slug_is_refused(tree):
    with pytest.raises(ValueError, match="only a-z"):
        await note_create(parent_code=tree["python"].code, slug="Тесты", title="Тесты")


async def test_nothing_is_added_to_a_deleted_codex_or_note(tree):
    await note_delete(tree["lint"].code)
    with pytest.raises(ValueError, match="neither a live codex nor a live note"):
        await note_create(parent_code=tree["lint"].code, slug="ruff", title="Ruff")

    await codex_delete(tree["python"].code)
    with pytest.raises(ValueError, match="deleted codex"):
        await note_create(parent_code=tree["python"].code, slug="new", title="Новое")


# ── edit and move ─────────────────────────────────────────────────────────────


async def test_fields_change_and_others_stay(tree):
    row = await note_update(tree["test"].code, body="Кратко о тестах")

    assert (row.body, row.title, row.slug) == ("Кратко о тестах", "Тесты", "test")


async def test_a_rename_to_a_sibling_slug_is_refused_and_to_its_own_is_not(tree):
    with pytest.raises(ValueError, match="taken under the codex 'python'"):
        await note_update(tree["lint"].code, slug="test")

    assert (await _row(tree["lint"].code)).slug == "lint"
    assert (await note_update(tree["lint"].code, slug="lint", title="Ruff")).title == "Ruff"


async def test_a_move_carries_the_branch_and_lands_at_the_end(tree):
    await note_update(tree["fixtures"].code, parent_code=tree["lint"].code)

    assert (await _row(tree["fixtures"].code)).parent_code == tree["lint"].code
    assert (await _row(tree["factories"].code)).parent_code == tree["fixtures"].code


async def test_a_move_under_its_own_branch_is_a_loop(tree):
    with pytest.raises(ValueError, match="inside its own branch"):
        await note_update(tree["test"].code, parent_code=tree["factories"].code)
    with pytest.raises(ValueError, match="inside its own branch"):
        await note_update(tree["test"].code, parent_code=tree["test"].code)

    assert (await _row(tree["test"].code)).parent_code is None


async def test_a_move_counts_the_height_of_the_moved_branch(tree):
    """``test`` is a branch of three levels; under ``lint`` (2) it would reach 5."""
    with pytest.raises(ValueError, match="reach 5 levels, the limit is 4"):
        await note_update(tree["test"].code, parent_code=tree["lint"].code)
    assert (await _row(tree["test"].code)).parent_code is None

    await note_update(tree["fixtures"].code, parent_code=tree["lint"].code)
    await note_update(tree["test"].code, parent_code=tree["lint"].code)


async def test_a_move_to_another_codex_is_refused(tree):
    vue = await codex_create(slug="vue", title="Vue")

    with pytest.raises(ValueError, match="moves only within its codex, not into 'vue'"):
        await note_update(tree["lint"].code, parent_code=vue.code)
    assert (await _row(tree["lint"].code)).codex_code == tree["python"].code


async def test_a_move_into_a_row_holding_the_slug_is_refused(tree):
    await note_create(parent_code=tree["lint"].code, slug="fixtures", title="Фикстуры линтера")

    with pytest.raises(ValueError, match="taken under the note 'lint'"):
        await note_update(tree["fixtures"].code, parent_code=tree["lint"].code)
    assert (await _row(tree["fixtures"].code)).parent_code == tree["test"].code


async def test_a_move_to_the_top_level_goes_through_the_codex(tree):
    await note_update(tree["factories"].code, parent_code=tree["python"].code)

    assert (await _row(tree["factories"].code)).parent_code is None
    assert await _order(tree["python"].code, None) == ["test", "lint", "factories"]


async def test_after_places_among_siblings(tree):
    await note_update(tree["lint"].code, after_code=None)
    assert await _order(tree["python"].code, None) == ["lint", "test"]

    await note_update(tree["lint"].code, after_code=tree["test"].code)
    assert await _order(tree["python"].code, None) == ["test", "lint"]


async def test_after_a_note_of_another_row_is_refused(tree):
    with pytest.raises(ValueError, match="not a sibling"):
        await note_update(tree["lint"].code, after_code=tree["fixtures"].code)


async def test_a_move_with_a_place_lands_there(tree):
    await note_update(tree["factories"].code, parent_code=tree["python"].code, after_code=None)

    assert await _order(tree["python"].code, None) == ["factories", "test", "lint"]


# ── delete and restore ────────────────────────────────────────────────────────


async def test_a_note_with_live_children_is_not_deleted_alone(tree):
    with pytest.raises(ValueError, match=f"1 live child note\\(s\\): CODEX@{tree['fixtures'].code} \\(fixtures\\)"):
        await note_delete(tree["test"].code)

    assert (await _row(tree["test"].code)).deleted_at is None
    assert await note_delete(tree["lint"].code)


async def test_a_branch_goes_under_one_mark_and_comes_back_whole(tree):
    await note_delete(tree["test"].code, with_branch=True)

    marks = {(await _row(tree[k].code)).deleted_at for k in ("test", "fixtures", "factories")}
    assert len(marks) == 1 and None not in marks

    assert await note_restore(tree["test"].code)
    for key in ("test", "fixtures", "factories"):
        assert (await _row(tree[key].code)).deleted_at is None, key


async def test_a_restore_leaves_an_earlier_separate_deletion_deleted(tree):
    await note_delete(tree["factories"].code)
    await note_delete(tree["test"].code, with_branch=True)

    await note_restore(tree["test"].code)
    assert (await _row(tree["fixtures"].code)).deleted_at is None
    assert (await _row(tree["factories"].code)).deleted_at is not None


async def test_a_deleted_note_frees_its_slug_and_its_restore_is_refused_while_taken(tree):
    await note_delete(tree["lint"].code)
    await note_create(parent_code=tree["python"].code, slug="lint", title="Новый линтер")

    with pytest.raises(ValueError, match="taken under the codex 'python'"):
        await note_restore(tree["lint"].code)
    assert (await _row(tree["lint"].code)).deleted_at is not None


async def test_a_note_under_a_deleted_parent_is_not_restored_alone(tree):
    await note_delete(tree["factories"].code)
    await note_delete(tree["test"].code, with_branch=True)

    with pytest.raises(ValueError, match="under a deleted note"):
        await note_restore(tree["factories"].code)
    assert (await _row(tree["factories"].code)).deleted_at is not None


async def test_a_restore_that_would_overflow_the_depth_is_refused(tree):
    """``factories`` left alone; then its branch's root moved deeper — bringing it back would make
    five levels."""
    await note_delete(tree["factories"].code)
    await note_update(tree["test"].code, parent_code=tree["lint"].code)

    with pytest.raises(ValueError, match="reach 5 levels"):
        await note_restore(tree["factories"].code)
    assert (await _row(tree["factories"].code)).deleted_at is not None


async def test_a_hard_delete_of_a_branch_removes_every_row(tree):
    await note_delete(tree["test"].code, with_branch=True, hard=True)

    for key in ("test", "fixtures", "factories"):
        assert await _row(tree[key].code) is None, key
    assert await _row(tree["lint"].code) is not None


async def test_edits_of_a_deleted_note_return_none(tree):
    await note_delete(tree["lint"].code)

    assert await note_update(tree["lint"].code, title="Правка") is None
    assert not await note_restore(tree["test"].code)
