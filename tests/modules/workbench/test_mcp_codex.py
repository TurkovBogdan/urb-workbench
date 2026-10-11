"""workbench MCP: the codexes as the agent sees them — one canvas of mounted codexes.

Called exactly as the agent calls: codes with ``CODEX@``, paths from the canvas root, refusals as
``ToolError``. Every refusal of a write is followed by a read past the tools: a tool that refuses
after writing tells the agent "nothing happened" while something did.

The canvas of the bound workspace ``Работа``::

    python   (mounted, agent may write)
      test   — «Стандарт тестирования»
        fixtures
    vue      (mounted, read-only for the agent)
      test
    sql      (mounted only into ``Личное``)
"""

from __future__ import annotations

import pytest
from fastmcp.exceptions import ToolError

from src.modules.codex.crud import codex as codex_crud
from src.modules.codex.crud import mount as mount_crud
from src.modules.codex.crud import note as note_crud
from src.modules.workspace.crud.workspace import workspace_create

pytestmark = pytest.mark.db


@pytest.fixture
async def canvas(call, workspace):
    python = await codex_crud.codex_create(
        slug="python", title="Python", description="Бэкенд на Python", body="Правила Python"
    )
    vue = await codex_crud.codex_create(slug="vue", title="Vue")
    sql = await codex_crud.codex_create(slug="sql", title="SQL")
    test = await note_crud.note_create(
        parent_code=python.code, slug="test", title="Тесты", description="Стандарт тестирования"
    )
    fixtures = await note_crud.note_create(
        parent_code=test.code, slug="fixtures", title="Фикстуры", body="Фикстура pytest"
    )
    vue_test = await note_crud.note_create(parent_code=vue.code, slug="test", title="Тесты Vue")
    await mount_crud.mount_add(python.code, workspace.code)
    await mount_crud.mount_add(vue.code, workspace.code, agent_can_edit=False)
    personal = await workspace_create(title="Личное")
    await mount_crud.mount_add(sql.code, personal.code)
    await call("workspace_use", workspace_code=workspace.code)
    return {
        "python": python.code,
        "vue": vue.code,
        "sql": sql.code,
        "test": test.code,
        "fixtures": fixtures.code,
        "vue_test": vue_test.code,
    }


def c(bare: str) -> str:
    return f"CODEX@{bare}"


async def _body(bare: str) -> str:
    return (await note_crud.note_get(bare, include_deleted=True)).body


# ── reading ───────────────────────────────────────────────────────────────────


async def test_the_index_is_the_mounted_codexes_with_the_agent_right(call, canvas):
    answer = await call("codex_index")

    assert answer["workspace_title"] == "Работа"
    assert [(r["slug"], r["agent_can_edit"]) for r in answer["codexes"]] == [
        ("python", True),
        ("vue", False),
    ]
    assert answer["codexes"][0]["code"] == c(canvas["python"])


@pytest.mark.parametrize("codex", ["python", "CODEX@{python}"])
async def test_rules_by_slug_or_code(call, canvas, codex):
    answer = await call("codex_rules", codex=codex.format(**canvas))

    assert (answer["slug"], answer["rules"]) == ("python", "Правила Python")


async def test_rules_of_a_note_point_at_its_codex(call, canvas):
    with pytest.raises(ToolError, match="a note of the codex 'python' — the rules are codex_rules\\('python'\\)"):
        await call("codex_rules", codex=c(canvas["test"]))
    with pytest.raises(ToolError, match="is a path into a codex"):
        await call("codex_rules", codex="python/test")


async def test_get_a_note_by_path_whole_with_its_children(call, canvas):
    answer = await call("codex_get", target="python/test")

    assert (answer["kind"], answer["path"], answer["code"]) == ("note", "python/test", c(canvas["test"]))
    assert answer["parent_code"] == c(canvas["python"])
    assert answer["writable"] is True
    assert [(ch["slug"], ch["children"]) for ch in answer["children"]] == [("fixtures", 0)]
    assert "body" not in answer["children"][0]


async def test_get_a_codex_carries_no_rules_and_says_read_only(call, canvas):
    answer = await call("codex_get", target=c(canvas["vue"]))

    assert (answer["kind"], answer["body"], answer["writable"]) == ("codex", "", False)
    assert [ch["slug"] for ch in answer["children"]] == ["test"]


@pytest.mark.parametrize("root", ["", "/"])
async def test_get_of_the_root_points_at_the_index(call, canvas, root):
    with pytest.raises(ToolError, match="codex_index lists the mounted codexes"):
        await call("codex_get", target=root)


async def test_a_codex_mounted_elsewhere_is_not_here_by_code_path_or_search(call, canvas):
    with pytest.raises(ToolError, match="not in a codex mounted into 'Работа'"):
        await call("codex_get", target=c(canvas["sql"]))
    with pytest.raises(ToolError, match="Nothing at the path 'sql'"):
        await call("codex_get", target="sql")
    assert (await call("codex_search", query="SQL"))["hits"] == []


async def test_a_missing_code_is_said_to_be_missing(call, canvas):
    with pytest.raises(ToolError, match="CODEX@0000000000 does not exist"):
        await call("codex_get", target="CODEX@0000000000")


async def test_the_tree_from_the_root_and_from_a_note(call, canvas):
    whole = await call("codex_tree")
    assert whole["root"] == "/"
    assert [n["slug"] for n in whole["nodes"]] == ["python", "vue"]
    assert [n["slug"] for n in whole["nodes"][0]["children"][0]["children"]] == ["fixtures"]

    branch = await call("codex_tree", target="python/test")
    assert branch["root"] == "python/test"
    assert [n["slug"] for n in branch["nodes"]] == ["test"]


async def test_search_in_any_case_and_within_a_branch(call, canvas):
    hits = (await call("codex_search", query="ТЕСТИРОВАНИЯ"))["hits"]
    assert [h["path"] for h in hits] == ["python/test"]
    assert "Стандарт тестирования" in hits[0]["fragment"]

    assert [h["path"] for h in (await call("codex_search", query="тесты", path="vue"))["hits"]] == [
        "vue/test"
    ]


# ── writing ───────────────────────────────────────────────────────────────────


async def test_add_under_a_path_and_read_it_back(call, canvas):
    added = await call(
        "codex_add", parent="python/test", slug="factories", title="Фабрики", body="Текст"
    )

    assert added["path"] == "python/test/factories"
    got = await call("codex_get", target=added["code"])
    assert (got["body"], got["parent_code"]) == ("Текст", c(canvas["test"]))


async def test_add_into_the_root_is_the_persons(call, canvas):
    with pytest.raises(ToolError, match="created and mounted by the person"):
        await call("codex_add", parent="/", slug="go", title="Go")
    assert [n["slug"] for n in (await call("codex_tree"))["nodes"]] == ["python", "vue"]


async def test_the_depth_limit_reaches_the_agent(call, canvas):
    await call("codex_add", parent="python/test/fixtures", slug="pytest", title="Pytest")

    with pytest.raises(ToolError, match="reach 5 levels, the limit is 4"):
        await call("codex_add", parent="python/test/fixtures/pytest", slug="deep", title="Глубже")


async def test_a_read_only_mount_refuses_every_write_and_writes_nothing(call, canvas):
    vue_test = c(canvas["vue_test"])

    with pytest.raises(ToolError, match="'vue' .* is read-only for you in 'Работа'"):
        await call("codex_add", parent="vue", slug="unit", title="Юнит")
    with pytest.raises(ToolError, match="read-only"):
        await call("codex_update", target=vue_test, title="Переименовано")
    with pytest.raises(ToolError, match="read-only"):
        await call("content_set", code=vue_test, field="body", text="Новый текст")
    with pytest.raises(ToolError, match="read-only"):
        await call("delete", code=vue_test)

    row = await note_crud.note_get(canvas["vue_test"])
    assert (row.title, row.body, row.deleted_at) == ("Тесты Vue", "", None)
    assert [n["slug"] for n in (await call("codex_get", target="vue"))["children"]] == ["test"]


async def test_a_codex_itself_is_refused_on_every_write(call, canvas):
    python = c(canvas["python"])

    with pytest.raises(ToolError, match="is a codex, not a note"):
        await call("codex_update", target=python, title="Питон")
    with pytest.raises(ToolError, match="is a codex, not a note"):
        await call("content_set", code=python, field="body", text="Новые правила")
    with pytest.raises(ToolError, match="is a codex, not a note"):
        await call("delete", code=python)

    codex = await codex_crud.codex_get(canvas["python"])
    assert (codex.title, codex.body, codex.deleted_at) == ("Python", "Правила Python", None)


async def test_update_renames_moves_and_places(call, canvas):
    lint = await call("codex_add", parent="python", slug="lint", title="Линтер")

    moved = await call("codex_update", target="python/test/fixtures", parent=lint["code"])
    assert moved["path"] == "python/lint/fixtures"

    renamed = await call("codex_update", target=moved["code"], slug="fixture-rules")
    assert renamed["path"] == "python/lint/fixture-rules"

    await call("codex_update", target=lint["code"], after="start")
    tree = await call("codex_tree", target="python")
    assert [n["slug"] for n in tree["nodes"][0]["children"]] == ["lint", "test"]


async def test_a_move_into_another_codex_is_refused(call, canvas):
    with pytest.raises(ToolError, match="moves only within its codex"):
        await call("codex_update", target="python/test", parent="vue")
    assert (await note_crud.note_get(canvas["test"])).codex_code == canvas["python"]


async def test_content_edits_the_note_body(call, canvas):
    await call("content_add", code=c(canvas["fixtures"]), field="body", text="\nЕщё", position="end")

    assert await _body(canvas["fixtures"]) == "Фикстура pytest\nЕщё"


async def test_a_note_with_children_is_deleted_only_after_them(call, canvas):
    with pytest.raises(ToolError, match=f"live child notes: CODEX@{canvas['fixtures']} \\(fixtures\\)"):
        await call("delete", code=c(canvas["test"]))
    assert (await note_crud.note_get(canvas["test"])) is not None

    assert await call("delete", code=c(canvas["fixtures"]))
    assert await call("delete", code=c(canvas["test"]))
    assert (await call("codex_get", target="python"))["children"] == []


async def test_the_fence_sees_a_codex_and_its_notes_only_through_a_mount_here(call, canvas):
    """The fence answers on its own: reads go through the canvas and writes through the mount
    check, so without this test a broken fence would hide behind both."""
    from src.modules.workbench.scope import require_scope

    assert (await require_scope("CODEX", canvas["fixtures"])).title == "Работа"
    assert (await require_scope("CODEX", canvas["vue"])).title == "Работа"
    with pytest.raises(ValueError, match="not in a codex mounted into 'Работа'"):
        await require_scope("CODEX", canvas["sql"])
    await require_scope("CODEX", "0000000000")


async def test_writes_to_a_codex_mounted_elsewhere_are_refused_by_the_fence(call, canvas):
    sql_note = await note_crud.note_create(parent_code=canvas["sql"], slug="joins", title="Joins")

    with pytest.raises(ToolError, match="not in a codex mounted into 'Работа'"):
        await call("content_set", code=c(sql_note.code), field="body", text="Чужое")
    with pytest.raises(ToolError, match="not in a codex mounted into 'Работа'"):
        await call("delete", code=c(sql_note.code))
    row = await note_crud.note_get(sql_note.code)
    assert (row.body, row.deleted_at) == ("", None)
