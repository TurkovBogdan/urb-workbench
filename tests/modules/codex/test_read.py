"""Reading the canvas: paths that follow moves and renames, a node by code or by path, children
with their counts, the tree, and search in any case — all of it only within mounted codexes.

The fixture canvas of ``workspace`` — two mounted codexes, one unmounted::

    python                      (mounted)
      test
        fixtures — «Фикстуры pytest»
      lint
    vue                         (mounted)
      test
    sql                         (not mounted)
      joins
"""

from __future__ import annotations

import pytest

from src.core.database import write_scope
from src.core.utils.date import utc_now
from src.modules.codex.crud.codex import codex_create, codex_update
from src.modules.codex.crud.mount import mount_add
from src.modules.codex.crud.note import note_create, note_delete, note_update
from src.modules.codex.crud.read import children_of, resolve, search, subtree
from src.modules.codex.models import CodexNote
from src.modules.workspace.crud.workspace import workspace_create

pytestmark = pytest.mark.db


@pytest.fixture
async def canvas(workspace):
    python = await codex_create(slug="python", title="Python", body="Правила Python")
    vue = await codex_create(slug="vue", title="Vue")
    sql = await codex_create(slug="sql", title="SQL")
    test = await note_create(
        parent_code=python.code, slug="test", title="Тесты", description="Стандарт тестирования"
    )
    fixtures = await note_create(
        parent_code=test.code, slug="fixtures", title="Фикстуры pytest", body="Фикстура — это…"
    )
    lint = await note_create(parent_code=python.code, slug="lint", title="Линтер")
    vue_test = await note_create(parent_code=vue.code, slug="test", title="Тесты Vue")
    joins = await note_create(parent_code=sql.code, slug="joins", title="Соединения")
    for codex in (python, vue):
        await mount_add(codex.code, workspace.code)
    return {
        "ws": workspace.code,
        "python": python,
        "vue": vue,
        "sql": sql,
        "test": test,
        "fixtures": fixtures,
        "lint": lint,
        "vue_test": vue_test,
        "joins": joins,
    }


# ── resolve ───────────────────────────────────────────────────────────────────


@pytest.mark.parametrize("target", ["python/test/fixtures", "/python/test/fixtures/"])
async def test_a_path_leads_to_its_note(canvas, target):
    node = await resolve(canvas["ws"], target)

    assert node.code == canvas["fixtures"].code
    assert (node.path, node.depth) == ("python/test/fixtures", 3)


async def test_a_code_in_any_case_leads_to_the_same_node(canvas):
    node = await resolve(canvas["ws"], f"codex@{canvas['fixtures'].code.lower()}")

    assert node.path == "python/test/fixtures"


async def test_a_codex_resolves_as_the_root_of_its_paths(canvas):
    by_code = await resolve(canvas["ws"], f"CODEX@{canvas['python'].code}")
    by_path = await resolve(canvas["ws"], "python")

    assert by_code.is_codex and by_path.is_codex
    assert (by_code.path, by_code.depth) == ("python", 1)


async def test_one_slug_in_two_codexes_is_two_nodes(canvas):
    assert (await resolve(canvas["ws"], "vue/test")).code == canvas["vue_test"].code
    assert (await resolve(canvas["ws"], "python/test")).code == canvas["test"].code


async def test_an_unmounted_codex_is_found_neither_by_path_nor_by_code(canvas):
    assert await resolve(canvas["ws"], "sql/joins") is None
    assert await resolve(canvas["ws"], f"CODEX@{canvas['joins'].code}") is None
    assert await resolve(canvas["ws"], f"CODEX@{canvas['sql'].code}") is None

    await mount_add(canvas["sql"].code, canvas["ws"])
    assert (await resolve(canvas["ws"], "sql/joins")).code == canvas["joins"].code


async def test_a_codex_mounted_only_elsewhere_stays_unseen_here(canvas):
    elsewhere = await workspace_create(title="Личное")
    await mount_add(canvas["sql"].code, elsewhere.code)

    assert await resolve(canvas["ws"], "sql/joins") is None
    assert await search(canvas["ws"], "соединения") == []
    assert (await resolve(elsewhere.code, "sql/joins")).code == canvas["joins"].code


async def test_a_note_whose_ancestor_was_deleted_past_the_service_is_cut_off(canvas):
    """The service never leaves a live note under a deleted one; a row that got there some other
    way must not surface with a path through a note that is gone."""
    async with write_scope() as s:
        (await s.get(CodexNote, canvas["test"].code)).deleted_at = utc_now()

    assert await resolve(canvas["ws"], f"CODEX@{canvas['fixtures'].code}") is None
    assert [h.node.path for h in await search(canvas["ws"], "pytest")] == []
    assert (await resolve(canvas["ws"], "python/lint")) is not None


async def test_a_path_that_does_not_exist_is_none(canvas):
    assert await resolve(canvas["ws"], "python/test/nothing") is None
    assert await resolve(canvas["ws"], "nothing") is None


@pytest.mark.parametrize("root", ["", "/", "  "])
async def test_the_root_is_not_a_node(canvas, root):
    with pytest.raises(ValueError, match="canvas root"):
        await resolve(canvas["ws"], root)


async def test_a_foreign_code_is_a_wrong_argument(canvas):
    with pytest.raises(ValueError, match="TASK@ reference, but a CODEX@ code"):
        await resolve(canvas["ws"], "TASK@0000000000")


async def test_a_path_follows_a_move_and_a_rename(canvas):
    await note_update(canvas["fixtures"].code, parent_code=canvas["lint"].code)
    await codex_update(canvas["python"].code, slug="py")

    node = await resolve(canvas["ws"], f"CODEX@{canvas['fixtures'].code}")
    assert node.path == "py/lint/fixtures"
    assert await resolve(canvas["ws"], "python/test/fixtures") is None


async def test_a_deleted_note_and_its_branch_are_gone_from_the_canvas(canvas):
    await note_delete(canvas["test"].code, with_branch=True)

    assert await resolve(canvas["ws"], "python/test") is None
    assert await resolve(canvas["ws"], f"CODEX@{canvas['fixtures'].code}") is None


# ── children and tree ─────────────────────────────────────────────────────────


async def test_children_come_in_order_with_their_own_counts(canvas):
    children = await children_of(canvas["ws"], "python")

    assert [(c.node.path, c.child_count) for c in children] == [("python/test", 1), ("python/lint", 0)]


async def test_children_of_what_is_not_in_the_canvas_is_none(canvas):
    assert await children_of(canvas["ws"], "sql") is None


async def test_the_tree_from_the_root_holds_every_mounted_codex(canvas):
    forest = await subtree(canvas["ws"])

    def flat(branch, out):
        out.append(branch.node.path)
        for child in branch.children:
            flat(child, out)
        return out

    assert [flat(b, []) for b in forest] == [
        ["python", "python/test", "python/test/fixtures", "python/lint"],
        ["vue", "vue/test"],
    ]


async def test_the_tree_from_a_note_is_its_branch(canvas):
    (branch,) = await subtree(canvas["ws"], "python/test")

    assert branch.node.path == "python/test"
    assert [c.node.path for c in branch.children] == ["python/test/fixtures"]
    assert await subtree(canvas["ws"], "sql") is None


# ── search ────────────────────────────────────────────────────────────────────


async def test_search_matches_cyrillic_in_any_case(canvas):
    hits = await search(canvas["ws"], "ТЕСТИРОВАНИЯ")

    assert [h.node.path for h in hits] == ["python/test"]
    assert "Стандарт тестирования" in hits[0].fragment


async def test_search_reaches_titles_texts_and_codexes(canvas):
    hits = await search(canvas["ws"], "pytest")
    assert [h.node.path for h in hits] == ["python/test/fixtures"]

    rules = await search(canvas["ws"], "правила python")
    assert [h.node.path for h in rules] == ["python"]


async def test_search_stays_within_the_canvas_and_the_branch(canvas):
    assert await search(canvas["ws"], "соединения") == []
    assert [h.node.path for h in await search(canvas["ws"], "тесты")] == [
        "python/test",
        "vue/test",
    ]
    assert [h.node.path for h in await search(canvas["ws"], "тесты", under="vue")] == ["vue/test"]
    assert await search(canvas["ws"], "тесты", under="sql") is None


async def test_an_empty_query_is_refused(canvas):
    with pytest.raises(ValueError, match="query is empty"):
        await search(canvas["ws"], "  ")
