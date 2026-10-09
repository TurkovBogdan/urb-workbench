"""workbench MCP: task notes — add, read, rename, edit, list, delete, and the workspace fence.

A task note is reached only through its task: a document no task holds, a deleted one and one in
another workspace are all refused, and each refusal is checked against the data after it.
"""

from __future__ import annotations

import pytest
from fastmcp.exceptions import ToolError

from src.modules.notes.crud import note as notes_crud
from src.modules.tasks.crud import journal as journal_crud
from src.modules.tasks.crud import note as note_crud
from src.modules.tasks.crud import task as task_crud
from src.modules.workspace.crud.workspace import workspace_create

pytestmark = pytest.mark.db


@pytest.fixture
async def task(call, workspace):
    await call("workspace_use", workspace_code=workspace.code)
    return await task_crud.task_create(workspace_code=workspace.code, title="Тарифы")


async def test_add_then_read_whole_and_list_without_text(call, task):
    added = await call(
        "task_note_add",
        task_code=f"TASK@{task.code}",
        title="Схема тарифов",
        description="Открыть перед правкой расчёта",
        body="# Схема\n",
    )

    assert added["code"].startswith("NOTE@") and added["workspace"] == f"WORKSPACE@{task.workspace_code}"
    read = await call("task_note_get", note_code=added["code"])
    assert (read["task_code"], read["title"], read["body"]) == (
        f"TASK@{task.code}",
        "Схема тарифов",
        "# Схема\n",
    )
    detail = await call("task_get", task_code=f"TASK@{task.code}")
    assert [note["code"] for note in detail["notes"]] == [added["code"]]
    assert "body" not in detail["notes"][0]
    assert detail["notes"][0]["description"] == "Открыть перед правкой расчёта"


async def test_update_renames_and_leaves_the_text(call, task):
    note = await note_crud.task_note_add(task_code=task.code, title="Схема", body="текст")

    answer = await call(
        "task_note_update", note_code=f"NOTE@{note.code}", title="Схема v2", description=""
    )

    assert (answer["title"], answer["description"]) == ("Схема v2", "")
    stored = await notes_crud.note_get(note.code)
    assert (stored.title, stored.body) == ("Схема v2", "текст")


async def test_the_body_is_content(call, task):
    note = await note_crud.task_note_add(task_code=task.code, title="Схема", body="## А\nстарое\n")

    await call("content_replace", code=f"NOTE@{note.code}", field="body", find="старое", text="новое")

    assert (await notes_crud.note_get(note.code)).body == "## А\nновое\n"


async def test_delete_is_soft_and_the_note_leaves_the_task(call, task):
    note = await note_crud.task_note_add(task_code=task.code, title="Схема")

    assert (await call("delete", code=f"NOTE@{note.code}"))["result"] is True

    assert (await call("task_get", task_code=f"TASK@{task.code}"))["notes"] == []
    assert (await notes_crud.note_get(note.code, include_deleted=True)).deleted_at is not None
    with pytest.raises(ToolError, match="does not exist \\(or is deleted\\)"):
        await call("task_note_get", note_code=f"NOTE@{note.code}")
    with pytest.raises(ToolError, match="is deleted"):
        await call("content_set", code=f"NOTE@{note.code}", field="body", text="х")


async def test_a_deleted_task_s_notes_are_read_but_not_changed(call, task):
    """A deleted task is the person's to restore, and its notes with it: every write is refused
    the way ``content_*`` refuses, reading stays open — the agent may need to say what was there."""
    note = await note_crud.task_note_add(task_code=task.code, title="Схема", body="текст")
    code = f"NOTE@{note.code}"
    await task_crud.task_delete(task.code)

    for tool, args in (
        ("task_note_update", {"note_code": code, "title": "Переименовал"}),
        ("content_set", {"code": code, "field": "body", "text": "переписал"}),
        ("delete", {"code": code}),
        ("task_note_add", {"task_code": f"TASK@{task.code}", "title": "Ещё"}),
    ):
        with pytest.raises(ToolError, match=f"TASK@{task.code}"):
            await call(tool, **args)

    stored = await notes_crud.note_get(note.code)
    assert (stored.title, stored.body, stored.deleted_at) == ("Схема", "текст", None)
    assert [n.code for n in await note_crud.task_note_list(task.code)] == [note.code]
    assert (await call("task_note_get", note_code=code))["body"] == "текст"


async def test_a_note_no_task_holds_does_not_exist_for_the_agent(call, task):
    orphan = await notes_crud.note_create(title="Ничей", body="текст")
    code = f"NOTE@{orphan.code}"

    for tool, args in (
        ("task_note_get", {"note_code": code}),
        ("task_note_update", {"note_code": code, "title": "Мой"}),
        ("content_set", {"code": code, "field": "body", "text": "х"}),
    ):
        with pytest.raises(ToolError, match="does not exist"):
            await call(tool, **args)
    assert (await call("delete", code=code))["result"] is False

    stored = await notes_crud.note_get(orphan.code)
    assert (stored.title, stored.body, stored.deleted_at) == ("Ничей", "текст", None)


async def test_a_note_of_another_workspace_is_refused_by_name(call, task):
    other = await workspace_create(title="Личное")
    foreign_task = await task_crud.task_create(workspace_code=other.code, title="Чужая")
    foreign = await note_crud.task_note_add(task_code=foreign_task.code, title="Чужая схема", body="т")
    code = f"NOTE@{foreign.code}"

    for tool, args in (
        ("task_note_get", {"note_code": code}),
        ("task_note_update", {"note_code": code, "title": "Моя"}),
        ("content_set", {"code": code, "field": "body", "text": "х"}),
        ("delete", {"code": code}),
        ("task_note_add", {"task_code": f"TASK@{foreign_task.code}", "title": "Подкинутая"}),
    ):
        with pytest.raises(ToolError, match="Личное"):
            await call(tool, **args)

    stored = await notes_crud.note_get(foreign.code)
    assert (stored.title, stored.body, stored.deleted_at) == ("Чужая схема", "т", None)
    assert [note.code for note in await note_crud.task_note_list(foreign_task.code)] == [foreign.code]


# The arguments that may carry a NOTE@ or a JOURNAL@, by name, and what else each tool needs.
_NOTE_OR_JOURNAL = {"code", "note_code", "journal_code"}
_REST = {
    "content_set": {"field": "body", "text": "х"},
    "content_replace": {"field": "body", "find": "а", "text": "б"},
    "content_set_section": {"field": "body", "heading": "# А", "text": "х"},
    "content_add": {"field": "body", "text": "х", "position": "end"},
    "delete": {},
    "interface_open": {},
    "journal_resolve": {"resolution": "х"},
    "task_note_get": {},
    "task_note_update": {"title": "х"},
}


async def test_an_entry_quoted_by_the_retired_note_word_is_refused_by_every_tool(
    call, mcp, task, monkeypatch
):
    """Swept from the server's own schemas: any argument that takes a NOTE@ or a JOURNAL@ meets
    an old journal code with the refusal that names the current one — and writes nothing."""
    monkeypatch.setattr("src.modules.tasks.mcp.interface.webbrowser.open", lambda url: True)
    await task_crud.task_update(task.code, type="standard")
    entry = await journal_crud.journal_create(task_code=task.code, type="decision", title="Б")
    swept = {
        (tool.name, name)
        for tool in await mcp.list_tools()
        for name in tool.inputSchema.get("properties", {})
        if name in _NOTE_OR_JOURNAL
    }

    assert {tool for tool, _ in swept} == set(_REST), "a new tool takes a NOTE@/JOURNAL@ — add it"
    assert len(swept) >= 9
    for tool, name in sorted(swept):
        with pytest.raises(ToolError, match=f"its code is JOURNAL@{entry.code}"):
            await call(tool, **{name: f"note@{entry.code.lower()}", **_REST[tool]})

    stored = await journal_crud.journal_get(entry.code)
    assert (stored.body, stored.resolution) == ("", "")


async def test_the_tools_are_named_after_the_task_note(mcp):
    names = {tool.name for tool in await mcp.list_tools()}

    assert {"task_note_add", "task_note_get", "task_note_update"} <= names
    assert not {name for name in names if name.startswith("note_")}
