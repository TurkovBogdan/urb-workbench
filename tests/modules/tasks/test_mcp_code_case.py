"""workbench MCP: every code parameter takes a code in any case and every answer is upper case.

Codes went upper case in storage (``tsm_007_codes_upper``); agents, client configs and notes still
hold the lower-case form. The promise is that nothing about an agent's behaviour changes: each
tool that takes a code finds its row whatever the case, and answers in the stored form.

The cases below call each tool with every code argument lower-cased — prefix and hash. The guard
at the bottom reads the server's own schemas, so a new code parameter that nobody covered here
fails the suite instead of shipping unchecked.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

import pytest

from src.modules.tasks.crud import group as group_crud
from src.modules.tasks.crud import note as note_crud
from src.modules.tasks.crud import stage as stage_crud
from src.modules.tasks.crud import task as task_crud

pytestmark = pytest.mark.db

_CODE_IN_TEXT = re.compile(r"\b(?:WORKSPACE|GROUP|TASK|STAGE|NOTE)@([0-9A-Za-z]{10})", re.IGNORECASE)


@dataclass
class World:
    workspace: str
    group_a: str
    group_b: str
    staged: str
    plain: str
    stage: str
    note: str


def low(prefix: str, bare: str) -> str:
    return f"{prefix}@{bare}".lower()


@pytest.fixture
def no_browser(monkeypatch):
    monkeypatch.setattr(
        "src.modules.tasks.mcp.interface.webbrowser.open", lambda url: True
    )


@pytest.fixture
async def world(call, workspace) -> World:
    a = await group_crud.group_create(workspace_code=workspace.code, title="Биллинг")
    b = await group_crud.group_create(workspace_code=workspace.code, title="Инфра")
    staged = await task_crud.task_create(
        workspace_code=workspace.code,
        title="Эпик",
        group_code=a.code,
        type="extended",
        body="# Plan\n\nalpha\n",
    )
    plain = await task_crud.task_create(
        workspace_code=workspace.code, title="Счета", group_code=a.code, type="standard"
    )
    stage = await stage_crud.stage_create(task_code=staged.code, title="Модели")
    note = await note_crud.note_create(task_code=staged.code, type="decision", title="Почему так")
    await call("workspace_use", workspace_code=low("WORKSPACE", workspace.code))
    return World(workspace.code, a.code, b.code, staged.code, plain.code, stage.code, note.code)


# (tool, the code parameters it exercises, arguments built from the world)
CASES = [
    ("workspace_use", {"workspace_code"}, lambda w: {"workspace_code": low("WORKSPACE", w.workspace)}),
    ("group_create", {"place_after"}, lambda w: {"title": "Новая", "description": "—", "place_after": low("GROUP", w.group_a)}),
    ("group_create", {"place_before"}, lambda w: {"title": "Новая", "description": "—", "place_before": low("GROUP", w.group_a)}),
    ("group_update", {"group_code", "place_after"}, lambda w: {"group_code": low("GROUP", w.group_a), "place_after": low("GROUP", w.group_b)}),
    ("group_update", {"place_before"}, lambda w: {"group_code": low("GROUP", w.group_b), "place_before": low("GROUP", w.group_a)}),
    ("tasks_regroup", {"group_code", "task_codes"}, lambda w: {"group_code": low("GROUP", w.group_b), "task_codes": [low("TASK", w.plain)]}),
    ("tasks_list", {"group_code"}, lambda w: {"group_code": low("GROUP", w.group_a)}),
    ("task_get", {"task_code"}, lambda w: {"task_code": low("TASK", w.staged)}),
    ("task_create", {"group_code"}, lambda w: {"title": "Новая", "description": "—", "group_code": low("GROUP", w.group_b)}),
    ("task_create", {"parent_code"}, lambda w: {"title": "Под", "description": "—", "parent_code": low("TASK", w.staged)}),
    ("task_update", {"task_code", "group_code"}, lambda w: {"task_code": low("TASK", w.plain), "group_code": low("GROUP", w.group_b)}),
    ("task_update", {"parent_code"}, lambda w: {"task_code": low("TASK", w.plain), "parent_code": low("TASK", w.staged)}),
    ("task_status", {"task_code"}, lambda w: {"task_code": low("TASK", w.plain), "status": "planned"}),
    ("stage_add", {"task_code"}, lambda w: {"task_code": low("TASK", w.staged), "title": "Ещё"}),
    ("stage_update", {"stage_code"}, lambda w: {"stage_code": low("STAGE", w.stage), "title": "Модели и схема"}),
    ("stage_close", {"stage_code"}, lambda w: {"stage_code": low("STAGE", w.stage), "evidence": "pytest: 1 passed"}),
    ("note_add", {"task_code", "stage_code"}, lambda w: {"task_code": low("TASK", w.staged), "stage_code": low("STAGE", w.stage), "type": "fact", "title": "Факт"}),
    ("note_resolve", {"note_code"}, lambda w: {"note_code": low("NOTE", w.note), "resolution": "Решено"}),
    ("notes_list", {"task_code"}, lambda w: {"task_code": low("TASK", w.staged)}),
    ("body_set", {"code"}, lambda w: {"code": low("TASK", w.staged), "text": "# Plan\n\nbeta\n"}),
    ("body_replace", {"code"}, lambda w: {"code": low("TASK", w.staged), "find": "alpha", "text": "gamma"}),
    ("body_set_section", {"code"}, lambda w: {"code": low("TASK", w.staged), "heading": "# Plan", "text": "# Plan\n\ndelta\n"}),
    ("body_add", {"code"}, lambda w: {"code": low("TASK", w.staged), "text": "\nomega\n", "position": "end"}),
    ("delete", {"code"}, lambda w: {"code": low("STAGE", w.stage)}),
    ("interface_open", {"code"}, lambda w: {"code": low("NOTE", w.note)}),
]


def _codes_in(value) -> list[str]:
    if isinstance(value, str):
        return [m.group(0) for m in _CODE_IN_TEXT.finditer(value)]
    if isinstance(value, dict):
        return [c for v in value.values() for c in _codes_in(v)]
    if isinstance(value, list):
        return [c for v in value for c in _codes_in(v)]
    return []


@pytest.mark.parametrize(
    ("tool", "covers", "build"), CASES, ids=[f"{t}:{'+'.join(sorted(c))}" for t, c, _ in CASES]
)
async def test_a_lower_case_code_is_served_and_answered_in_upper_case(
    call, world, no_browser, tool, covers, build
):
    answer = await call(tool, **build(world))

    if tool == "delete":
        # The one tool that answers without a code: the row being gone is the evidence.
        assert answer == {"result": True}
        assert await stage_crud.stage_get(world.stage) is None
        return
    codes = _codes_in(answer)
    assert codes, f"{tool} answered with no code to check: {answer!r}"
    assert all(code == code.upper() for code in codes), codes


async def test_delete_of_a_task_takes_a_lower_case_code(call, world):
    await call("delete", code=low("TASK", world.plain))

    assert await task_crud.task_get(world.plain) is None


async def test_every_code_parameter_of_every_tool_is_covered(mcp):
    """A code parameter added later without a case here would ship with nobody checking it."""
    tools = await mcp.list_tools()
    declared = {
        (tool.name, param)
        for tool in tools
        for param in tool.inputSchema.get("properties", {})
        if param.endswith("code") or param.endswith("codes") or param.startswith("place_")
    }
    covered = {(tool, param) for tool, params, _ in CASES for param in params}

    assert declared == covered
