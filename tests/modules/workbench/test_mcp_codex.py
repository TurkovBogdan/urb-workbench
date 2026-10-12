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

``codex_rules`` is off the server (``tools/codex.py``); its tests call it on a server of their own
that registers it, so the implementation stays working for the day it comes back.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime

import pytest
from fastmcp import Client
from fastmcp.exceptions import ToolError
from fastmcp.server.middleware import Middleware
from sqlalchemy import update

from src.core.database import write_scope
from src.core.mcp.context import McpServerContext
from src.modules.codex.constants import BODY_MAX, DESCRIPTION_MAX, SEGMENT_MAX, TITLE_MAX
from src.modules.codex.crud import codex as codex_crud
from src.modules.codex.crud import mount as mount_crud
from src.modules.codex.crud import note as note_crud
from src.modules.codex.models import CodexNote
from src.modules.workbench.server import mcp_server
from src.modules.workbench.tools.codex import register_rules
from src.modules.workspace.crud.workspace import workspace_create

pytestmark = pytest.mark.db


@pytest.fixture
async def rules(db):
    """``codex_rules`` called as the agent would, on a server that registers it."""
    server = mcp_server(McpServerContext(auth=None, audit=Middleware(), allowed_hosts=[]))
    register_rules(server)
    async with Client(server) as client:

        async def _call(codexes: list[str]):
            return (await client.call_tool("codex_rules", {"codexes": codexes})).structured_content

        yield _call


@pytest.fixture
async def canvas(call, workspace):
    python = await codex_crud.codex_create(
        segment="python", title="Python", description="Бэкенд на Python", body="Правила Python"
    )
    vue = await codex_crud.codex_create(segment="vue", title="Vue")
    sql = await codex_crud.codex_create(segment="sql", title="SQL")
    test = await note_crud.note_create(
        parent_code=python.code, segment="test", title="Тесты", description="Стандарт тестирования"
    )
    fixtures = await note_crud.note_create(
        parent_code=test.code, segment="fixtures", title="Фикстуры", body="Фикстура pytest"
    )
    vue_test = await note_crud.note_create(parent_code=vue.code, segment="test", title="Тесты Vue")
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

    assert "workspace" not in answer and "workspace_title" not in answer
    assert [(r["path"], r["editable"]) for r in answer["codexes"]] == [
        ("/python", True),
        ("/vue", False),
    ]
    assert list(answer["codexes"][0].items()) == [
        ("code", c(canvas["python"])),
        ("path", "/python"),
        ("segment", "python"),
        ("title", "Python"),
        ("description", "Бэкенд на Python"),
        ("records", 2),
        ("editable", True),
    ]


async def test_records_count_live_reachable_notes_at_every_depth(call, canvas, workspace):
    await note_crud.note_create(parent_code=canvas["fixtures"], segment="pytest", title="Pytest")
    old = await note_crud.note_create(parent_code=canvas["python"], segment="old", title="Старое")
    await note_crud.note_delete(old.code)
    gone = await note_crud.note_create(parent_code=canvas["python"], segment="gone", title="Ушло")
    await note_crud.note_create(parent_code=gone.code, segment="orphan", title="Сирота")
    # Deleted alone, as if its child had been left behind: the child is cut off with it.
    async with write_scope() as s:
        await s.execute(
            update(CodexNote).where(CodexNote.code == gone.code).values(deleted_at=datetime.now(UTC))
        )
    empty = await codex_crud.codex_create(segment="go", title="Go")
    await mount_crud.mount_add(empty.code, workspace.code)

    rows = (await call("codex_index"))["codexes"]

    assert [(r["path"], r["records"]) for r in rows] == [("/python", 3), ("/vue", 1), ("/go", 0)]


async def test_the_index_follows_the_workspace_order_of_the_mounts(call, canvas, workspace):
    await mount_crud.mount_reorder(canvas["vue"], workspace.code, after_code=None)

    assert [r["path"] for r in (await call("codex_index"))["codexes"]] == ["/vue", "/python"]


async def test_codex_rules_is_off_the_server(mcp):
    names = {tool.name for tool in await mcp.list_tools()}

    assert "codex_rules" not in names
    assert {"codex_index", "codex_get", "codex_tree"} <= names


@pytest.mark.parametrize(
    "tool, field, limit",
    [
        ("codex_add", "segment", SEGMENT_MAX),
        ("codex_add", "title", TITLE_MAX),
        ("codex_add", "description", DESCRIPTION_MAX),
        ("codex_add", "body", BODY_MAX),
        ("codex_update", "segment", SEGMENT_MAX),
        ("codex_update", "title", TITLE_MAX),
        ("codex_update", "description", DESCRIPTION_MAX),
    ],
)
async def test_a_field_states_the_limit_the_service_holds(mcp, tool, field, limit):
    [listed] = [t for t in await mcp.list_tools() if t.name == tool]
    stated = listed.inputSchema["properties"][field]["description"]

    assert re.search(rf"up to {limit:,} characters".replace(",", " "), stated), stated


@pytest.mark.parametrize("codex", ["python", "/python", "CODEX@{python}"])
async def test_rules_of_one_codex_by_path_or_code_come_as_a_list_of_one(rules, canvas, codex):
    answer = await rules([codex.format(**canvas)])

    [kept] = answer["nodes"]
    assert list(answer) == ["nodes"]
    assert list(kept.items()) == [
        ("code", c(canvas["python"])),
        ("path", "/python"),
        ("segment", "python"),
        ("title", "Python"),
        ("rules", "Правила Python"),
    ]


async def test_rules_of_several_codexes_keep_the_order_asked_each_once(rules, canvas):
    answer = await rules(["/vue", c(canvas["python"]), "python", c(canvas["vue"])])

    assert [r["path"] for r in answer["nodes"]] == ["/vue", "/python"]


async def test_one_bad_item_refuses_the_whole_call_naming_every_fault(rules, canvas):
    with pytest.raises(ToolError) as refusal:
        await rules(["/python", "/go", c(canvas["sql"]), "CODEX@0000000000"])

    text = str(refusal.value)
    assert "No rules returned" in text
    assert "'/go'" in text
    assert f"{c(canvas['sql'])} is not in a codex mounted into 'Работа'" in text
    assert "CODEX@0000000000 does not exist" in text
    assert "'/python'" not in text


async def test_rules_of_a_note_point_at_its_codex(rules, canvas):
    with pytest.raises(ToolError, match="a note of the codex '/python' — ask for '/python'"):
        await rules([c(canvas["test"])])
    with pytest.raises(ToolError, match="'/python/test' is a path into a codex"):
        await rules(["python", "/python/test"])
    with pytest.raises(ToolError, match="Name at least one codex"):
        await rules([])


async def test_get_of_one_target_is_a_list_of_one_and_nothing_else(call, canvas):
    got = await call("codex_get", targets=["/python/test/fixtures"])

    assert list(got) == ["nodes"]
    [node] = got["nodes"]
    assert list(node.items()) == [
        ("code", c(canvas["fixtures"])),
        ("path", "/python/test/fixtures"),
        ("segment", "fixtures"),
        ("parent_code", c(canvas["test"])),
        ("title", "Фикстуры"),
        ("description", ""),
        ("body", "Фикстура pytest"),
    ]


async def test_get_of_several_mixed_targets_keeps_the_order_asked_each_once(call, canvas):
    got = await call(
        "codex_get",
        targets=[c(canvas["fixtures"]), "vue", "/python/test/fixtures", c(canvas["vue"]), "/python"],
    )

    assert [(n["path"], n["segment"]) for n in got["nodes"]] == [
        ("/python/test/fixtures", "fixtures"),
        ("/vue", "vue"),
        ("/python", "python"),
    ]
    assert all("kind" not in n for n in got["nodes"])


async def test_one_bad_target_refuses_the_whole_get_naming_every_fault(call, canvas):
    with pytest.raises(ToolError) as refusal:
        await call(
            "codex_get", targets=["/python/test", "/python/nope", "/", c(canvas["sql"])]
        )

    text = str(refusal.value)
    assert "Nothing returned" in text
    assert "Nothing at the path '/python/nope'" in text
    assert "The canvas root is not a codex or a note" in text
    assert f"{c(canvas['sql'])} is not in a codex mounted into 'Работа'" in text
    assert "'/python/test'" not in text


async def test_get_of_nothing_is_refused(call, canvas):
    with pytest.raises(ToolError, match="Name at least one codex or note"):
        await call("codex_get", targets=[])


async def test_get_a_note_by_path_whole_with_its_children(call, canvas):
    [answer] = (await call("codex_get", targets=["python/test"]))["nodes"]

    assert (answer["code"], answer["path"], answer["segment"]) == (
        c(canvas["test"]),
        "/python/test",
        "test",
    )
    assert answer["parent_code"] == c(canvas["python"])
    [child] = answer["children"]
    assert list(child.items()) == [
        ("code", c(canvas["fixtures"])),
        ("path", "/python/test/fixtures"),
        ("segment", "fixtures"),
        ("title", "Фикстуры"),
        ("description", ""),
    ]


async def test_a_child_with_children_carries_their_count(call, canvas):
    [python] = (await call("codex_get", targets=["/python"]))["nodes"]

    assert [(ch["path"], ch["children"]) for ch in python["children"]] == [("/python/test", 1)]


async def test_get_a_codex_carries_its_rules_as_body_and_no_parent(call, canvas):
    [answer] = (await call("codex_get", targets=[c(canvas["python"])]))["nodes"]

    assert list(answer.items()) == [
        ("code", c(canvas["python"])),
        ("path", "/python"),
        ("segment", "python"),
        ("parent_code", None),
        ("title", "Python"),
        ("description", "Бэкенд на Python"),
        ("body", "Правила Python"),
        (
            "children",
            [
                {
                    "code": c(canvas["test"]),
                    "path": "/python/test",
                    "segment": "test",
                    "title": "Тесты",
                    "description": "Стандарт тестирования",
                    "children": 1,
                }
            ],
        ),
    ]


@pytest.mark.parametrize("root", ["", "/"])
async def test_get_of_the_root_points_at_the_index(call, canvas, root):
    with pytest.raises(ToolError, match="codex_index lists the mounted codexes"):
        await call("codex_get", targets=[root])


async def test_a_codex_mounted_elsewhere_is_not_here_by_code_path_or_search(call, canvas):
    with pytest.raises(ToolError, match="not in a codex mounted into 'Работа'"):
        await call("codex_get", targets=[c(canvas["sql"])])
    with pytest.raises(ToolError, match="Nothing at the path '/sql'"):
        await call("codex_get", targets=["sql"])
    assert (await call("codex_search", query=["SQL"]))["hits"] == []


async def test_a_missing_code_is_said_to_be_missing(call, canvas):
    with pytest.raises(ToolError, match="CODEX@0000000000 does not exist"):
        await call("codex_get", targets=["CODEX@0000000000"])


async def test_the_tree_from_the_root_and_from_a_note(call, canvas):
    whole = await call("codex_tree")
    assert list(whole) == ["root", "nodes"]
    assert whole["root"] == "/"
    assert [n["path"] for n in whole["nodes"]] == ["/python", "/vue"]
    assert [n["path"] for n in whole["nodes"][0]["children"][0]["children"]] == [
        "/python/test/fixtures"
    ]
    assert whole["nodes"][0]["segment"] == "python"

    branch = await call("codex_tree", target="/python/test")
    assert branch == {
        "root": "/python/test",
        "nodes": [
            {
                "code": c(canvas["test"]),
                "path": "/python/test",
                "segment": "test",
                "title": "Тесты",
                "children": [
                    {
                        "code": c(canvas["fixtures"]),
                        "path": "/python/test/fixtures",
                        "segment": "fixtures",
                        "title": "Фикстуры",
                    }
                ],
            }
        ],
    }
    assert list(branch["nodes"][0]) == ["code", "path", "segment", "title", "children"]
    assert await call("codex_tree", target="/python/test", with_description=False) == branch


async def test_the_long_tree_carries_every_description_in_order(call, canvas):
    branch = await call("codex_tree", target="/python/test", with_description=True)

    [node] = branch["nodes"]
    assert list(node.items()) == [
        ("code", c(canvas["test"])),
        ("path", "/python/test"),
        ("segment", "test"),
        ("title", "Тесты"),
        ("description", "Стандарт тестирования"),
        (
            "children",
            [
                {
                    "code": c(canvas["fixtures"]),
                    "path": "/python/test/fixtures",
                    "segment": "fixtures",
                    "title": "Фикстуры",
                    "description": "",
                }
            ],
        ),
    ]


async def test_a_codex_without_notes_has_no_children_in_the_tree(call, canvas, workspace):
    go = await codex_crud.codex_create(segment="go", title="Go")
    await mount_crud.mount_add(go.code, workspace.code)

    tree = await call("codex_tree", target="go")
    assert tree["nodes"] == [{"code": c(go.code), "path": "/go", "segment": "go", "title": "Go"}]
    [node] = (await call("codex_get", targets=["/go"]))["nodes"]
    assert "children" not in node


async def test_search_in_any_case_and_within_a_branch(call, canvas):
    hits = (await call("codex_search", query=["ТЕСТИРОВАНИЯ"]))["hits"]
    assert [h["path"] for h in hits] == ["/python/test"]
    assert list(hits[0])[:3] == ["code", "path", "segment"]
    assert hits[0]["segment"] == "test"
    assert "Стандарт тестирования" in hits[0]["fragment"]

    in_vue = (await call("codex_search", query=["тесты"], within="vue"))["hits"]
    assert [h["path"] for h in in_vue] == ["/vue/test"]


async def test_search_within_a_node_includes_the_node_itself(call, canvas):
    hits = (await call("codex_search", query=["тест"], within=c(canvas["test"])))["hits"]

    assert [h["path"] for h in hits] == ["/python/test"]
    assert (await call("codex_search", query=["тест"], within="/python/test/fixtures"))[
        "hits"
    ] == []
    assert [
        h["path"] for h in (await call("codex_search", query=["тест"], within="/"))["hits"]
    ] == ["/python/test", "/vue/test"]


async def _found(call, query: list[str]) -> list[str]:
    return [h["path"] for h in (await call("codex_search", query=query))["hits"]]


async def test_search_variants_find_what_each_finds_alone_each_record_once(call, canvas):
    assert await _found(call, ["pytest"]) == ["/python/test/fixtures"]
    assert await _found(call, ["Стандарт"]) == ["/python/test"]
    assert await _found(call, ["pytest", "Стандарт"]) == ["/python/test", "/python/test/fixtures"]
    assert await _found(call, ["тест", "Тесты", "ТЕСТ"]) == ["/python/test", "/vue/test"]


async def test_search_with_one_matching_variant_and_blanks_dropped(call, canvas):
    assert await _found(call, ["нет-такого", "Фикстур"]) == ["/python/test/fixtures"]
    assert await _found(call, ["  ", "", "pytest"]) == ["/python/test/fixtures"]


@pytest.mark.parametrize("query", [[], ["  "], ["", "\t"]])
async def test_search_without_a_variant_is_refused(call, canvas, query):
    with pytest.raises(ToolError, match="`query` needs at least one non-blank variant"):
        await call("codex_search", query=query)


async def test_search_fragment_is_around_the_earliest_variant(call, canvas):
    body = "а" * 100 + " beta " + "б" * 100 + " alpha"
    await note_crud.note_create(
        parent_code=canvas["python"], segment="far", title="Далеко", body=body
    )

    [hit] = (await call("codex_search", query=["alpha", "beta"]))["hits"]

    assert "beta" in hit["fragment"] and "alpha" not in hit["fragment"]
    assert "variant" not in hit and "matched" not in hit


# ── writing ───────────────────────────────────────────────────────────────────


async def test_add_under_a_path_and_read_it_back(call, canvas):
    added = await call(
        "codex_add", parent="python/test", segment="factories", title="Фабрики", body="Текст"
    )

    assert (added["path"], added["segment"]) == ("/python/test/factories", "factories")
    assert list(added)[-3:] == ["code", "path", "segment"]
    [got] = (await call("codex_get", targets=[added["path"]]))["nodes"]
    assert (got["code"], got["body"], got["parent_code"]) == (
        added["code"],
        "Текст",
        c(canvas["test"]),
    )


async def test_add_into_the_root_is_the_persons(call, canvas):
    with pytest.raises(ToolError, match="created and mounted by the person"):
        await call("codex_add", parent="/", segment="go", title="Go")
    assert [n["path"] for n in (await call("codex_tree"))["nodes"]] == ["/python", "/vue"]


async def test_the_depth_limit_reaches_the_agent(call, canvas):
    await call("codex_add", parent="python/test/fixtures", segment="pytest", title="Pytest")

    with pytest.raises(ToolError, match="reach 5 levels, the limit is 4"):
        await call("codex_add", parent="python/test/fixtures/pytest", segment="deep", title="Глубже")


async def test_a_read_only_mount_refuses_every_write_and_writes_nothing(call, canvas):
    vue_test = c(canvas["vue_test"])
    named = f"'/vue' ({c(canvas['vue'])})"

    with pytest.raises(ToolError) as refusal:
        await call("codex_add", parent="vue", segment="unit", title="Юнит")
    text = str(refusal.value)
    assert f"The codex {named} is not editable for you in 'Работа'" in text
    assert f"Tell the user the codex {named} is read-only for you" in text
    with pytest.raises(ToolError, match="read-only"):
        await call("codex_update", target=vue_test, title="Переименовано")
    with pytest.raises(ToolError, match="read-only"):
        await call("content_set", code=vue_test, field="body", text="Новый текст")
    with pytest.raises(ToolError, match="read-only"):
        await call("delete", code=vue_test)

    row = await note_crud.note_get(canvas["vue_test"])
    assert (row.title, row.body, row.deleted_at) == ("Тесты Vue", "", None)
    [vue] = (await call("codex_get", targets=["vue"]))["nodes"]
    assert [n["path"] for n in vue["children"]] == ["/vue/test"]


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
    lint = await call("codex_add", parent="python", segment="lint", title="Линтер")

    moved = await call("codex_update", target="python/test/fixtures", parent=lint["code"])
    assert moved["path"] == "/python/lint/fixtures"

    renamed = await call("codex_update", target=moved["code"], segment="fixture-rules")
    assert (renamed["path"], renamed["segment"]) == ("/python/lint/fixture-rules", "fixture-rules")
    [read_back] = (await call("codex_get", targets=[renamed["code"]]))["nodes"]
    assert (read_back["path"], read_back["segment"]) == (renamed["path"], "fixture-rules")

    await call("codex_update", target=lint["code"], after="start")
    tree = await call("codex_tree", target="python")
    assert [n["path"] for n in tree["nodes"][0]["children"]] == ["/python/lint", "/python/test"]


async def test_a_move_into_another_codex_is_refused(call, canvas):
    with pytest.raises(ToolError, match="moves only within its codex, not into '/vue'"):
        await call("codex_update", target="python/test", parent="vue")
    assert (await note_crud.note_get(canvas["test"])).codex_code == canvas["python"]


async def test_content_by_a_path_points_at_the_code(call, canvas):
    with pytest.raises(ToolError, match="looks like a codex path — content_\\* takes the note's CODEX@ code; codex_get\\(\\['python/test'\\]\\)"):
        await call("content_add", code="python/test", field="body", text="х", position="end")
    assert await _body(canvas["test"]) == ""
    with pytest.raises(ToolError, match="looks like a codex path — delete takes the note's CODEX@ code"):
        await call("delete", code="python/test/fixtures")
    assert (await note_crud.note_get(canvas["fixtures"])) is not None


async def test_content_edits_the_note_body(call, canvas):
    await call("content_add", code=c(canvas["fixtures"]), field="body", text="\nЕщё", position="end")

    assert await _body(canvas["fixtures"]) == "Фикстура pytest\nЕщё"


async def test_a_note_with_children_is_deleted_only_after_them(call, canvas):
    with pytest.raises(ToolError, match=f"live child notes: CODEX@{canvas['fixtures']} \\(fixtures\\)"):
        await call("delete", code=c(canvas["test"]))
    assert (await note_crud.note_get(canvas["test"])) is not None

    assert await call("delete", code=c(canvas["fixtures"]))
    assert await call("delete", code=c(canvas["test"]))
    [python] = (await call("codex_get", targets=["python"]))["nodes"]
    assert "children" not in python


async def test_the_fence_sees_a_codex_and_its_notes_only_through_a_mount_here(call, canvas):
    """The fence answers on its own: reads go through the canvas and writes through the mount
    check, so without this test a broken fence would hide behind both."""
    from src.modules.workbench.scope import require_scope

    assert (await require_scope("CODEX", canvas["fixtures"])).title == "Работа"
    assert (await require_scope("CODEX", canvas["vue"])).title == "Работа"
    with pytest.raises(ValueError, match="not in a codex mounted into 'Работа'"):
        await require_scope("CODEX", canvas["sql"])
    await require_scope("CODEX", "0000000000")


async def test_interface_open_leads_to_the_codex_editor_on_the_node(call, canvas, monkeypatch):
    monkeypatch.setattr(
        "src.modules.workbench.tools.interface.webbrowser.open", lambda url: True
    )

    note = await call("interface_open", code=c(canvas["fixtures"]))
    codex = await call("interface_open", code=f"codex@{canvas['python'].lower()}")

    assert note["result"].endswith(f"/codex/materials/{c(canvas['fixtures'])}")
    assert codex["result"].endswith(f"/codex/materials/{c(canvas['python'])}")
    with pytest.raises(ToolError, match="not in a codex mounted into 'Работа'"):
        await call("interface_open", code=c(canvas["sql"]))


async def test_writes_to_a_codex_mounted_elsewhere_are_refused_by_the_fence(call, canvas):
    sql_note = await note_crud.note_create(parent_code=canvas["sql"], segment="joins", title="Joins")

    with pytest.raises(ToolError, match="not in a codex mounted into 'Работа'"):
        await call("content_set", code=c(sql_note.code), field="body", text="Чужое")
    with pytest.raises(ToolError, match="not in a codex mounted into 'Работа'"):
        await call("delete", code=c(sql_note.code))
    row = await note_crud.note_get(sql_note.code)
    assert (row.body, row.deleted_at) == ("", None)
