"""Task search: Cyrillic case and depth by scope.

Two different surfaces of one question, "where to search". The list's ``query`` searches the
title and the goal — those are visible in every row. The bodies (brief, plan with stages,
journal) are searched by ``task_search_codes``, and only in explicitly named scopes: a silent
search across eight-kilobyte bodies returns matches that don't tell you whether it's the right
task.

Case is tested with CYRILLIC on purpose: SQLite's ``lower()`` folds ASCII only, and a comparison
left in SQL would silently diverge from PostgreSQL — with Latin text such a test is green on
both.
"""

from __future__ import annotations

import pytest

from src.modules.tasks.constants import NOTE_DECISION, NOTE_FACT, TYPE_EXTENDED
from src.modules.tasks.crud.note import note_create, note_resolve
from src.modules.tasks.crud.stage import stage_create, stage_update
from src.modules.tasks.crud.task import (
    task_create,
    task_delete,
    task_list_by_workspace,
    task_search_codes,
)
from src.modules.workspace.crud.workspace import workspace_create

pytestmark = pytest.mark.db

SEARCH = "/internal/workbench/tasks/search"


# ── title and goal ────────────────────────────────────────────────────────────


async def test_query_over_title_and_goal_ignores_cyrillic_case(db, workspace):
    row = await task_create(
        workspace_code=workspace.code,
        title="Панель фильтров",
        description="Срез списка набирается за пару движений",
    )

    by_upper = await task_list_by_workspace(workspace.code, query="ПАНЕЛЬ")
    by_lower = await task_list_by_workspace(workspace.code, query="панель")
    by_goal = await task_list_by_workspace(workspace.code, query="СРЕЗ СПИСКА")

    assert [r.code for r in by_upper] == [row.code]
    assert [r.code for r in by_lower] == [row.code]
    assert [r.code for r in by_goal] == [row.code]


async def test_query_does_not_reach_the_bodies(db, workspace):
    """The list searches only what its row shows: a match in the plan does not widen its output."""
    await task_create(
        workspace_code=workspace.code,
        title="Панель фильтров",
        type=TYPE_EXTENDED,
        body="Ставлю SearchField первым в ряду",
    )

    assert await task_list_by_workspace(workspace.code, query="SearchField") == []


# ── depth by scope ────────────────────────────────────────────────────────────


async def test_scopes_are_off_until_asked(db, workspace):
    row = await task_create(
        workspace_code=workspace.code,
        title="Задача",
        type=TYPE_EXTENDED,
        context="Панель уже есть",
    )

    assert await task_search_codes(workspace.code, "панель") == []
    assert await task_search_codes(workspace.code, "", in_brief=True) == []
    assert await task_search_codes(workspace.code, "панель", in_brief=True) == [row.code]


async def test_brief_scope_covers_the_whole_brief(db, workspace):
    """The brief is four fields, and the title and the goal are not part of this scope."""
    context = await task_create(
        workspace_code=workspace.code, title="A", type=TYPE_EXTENDED, context="ищем тут"
    )
    constraints = await task_create(
        workspace_code=workspace.code, title="B", type=TYPE_EXTENDED, constraints="ИЩЕМ ТУТ"
    )
    criteria = await task_create(
        workspace_code=workspace.code, title="C", type=TYPE_EXTENDED, criteria="Ищем Тут"
    )

    found = await task_search_codes(workspace.code, "ищем тут", in_brief=True)

    assert found == sorted([context.code, constraints.code, criteria.code])


async def test_plan_scope_covers_the_stages_too(db, workspace):
    """The plan is the task body plus its stages' bodies: a work step is described there, not on
    the card."""
    planned = await task_create(
        workspace_code=workspace.code,
        title="С планом",
        type=TYPE_EXTENDED,
        body="Сначала бэк",
    )
    staged = await task_create(
        workspace_code=workspace.code, title="С этапом", type=TYPE_EXTENDED
    )
    await stage_create(task_code=staged.code, title="Шаг", body="Сначала бэк, потом панель")

    found = await task_search_codes(workspace.code, "СНАЧАЛА БЭК", in_plan=True)

    assert found == sorted([planned.code, staged.code])
    assert await task_search_codes(workspace.code, "сначала бэк", in_brief=True) == []


async def test_journal_scope_reads_the_notes(db, workspace):
    row = await task_create(
        workspace_code=workspace.code, title="С журналом", type=TYPE_EXTENDED
    )
    await note_create(
        task_code=row.code,
        type=NOTE_FACT,
        title="Замер до работы",
        body="1491 passed",
    )

    assert await task_search_codes(workspace.code, "1491", in_journal=True) == [row.code]
    assert await task_search_codes(workspace.code, "1491", in_plan=True) == []


async def test_plan_scope_reads_the_evidence_of_a_stage(db, workspace):
    """Evidence is as much the stage's text as its body: it is where one looks up "what closed
    this"."""
    row = await task_create(
        workspace_code=workspace.code, title="С доказательством", type=TYPE_EXTENDED
    )
    stage = await stage_create(task_code=row.code, title="Шаг")
    await stage_update(stage.code, evidence="pytest --core → 1491 passed")

    assert await task_search_codes(workspace.code, "1491 PASSED", in_plan=True) == [row.code]


async def test_journal_scope_reads_the_resolution(db, workspace):
    """An entry's resolution is half its meaning: "how it ended" is searched for on a par with
    "what it was about"."""
    row = await task_create(
        workspace_code=workspace.code, title="С решением", type=TYPE_EXTENDED
    )
    note = await note_create(
        task_code=row.code, type=NOTE_DECISION, title="Куда класть области поиска"
    )
    await note_resolve(note.code, "Переходник живёт в search.ts")

    assert await task_search_codes(workspace.code, "ПЕРЕХОДНИК", in_journal=True) == [row.code]


async def test_scopes_combine_and_a_task_comes_back_once(db, workspace):
    """Scopes are a union, not an intersection; a task that matches twice comes back as one row."""
    both = await task_create(
        workspace_code=workspace.code,
        title="И там, и там",
        type=TYPE_EXTENDED,
        context="общее слово",
    )
    await note_create(
        task_code=both.code, type=NOTE_FACT, title="И тут общее слово"
    )
    journal_only = await task_create(
        workspace_code=workspace.code, title="Только журнал", type=TYPE_EXTENDED
    )
    await note_create(
        task_code=journal_only.code, type=NOTE_FACT, title="И здесь общее слово"
    )

    found = await task_search_codes(
        workspace.code, "общее слово", in_brief=True, in_journal=True
    )

    assert found == sorted([both.code, journal_only.code])


async def test_search_stays_inside_its_workspace(db, workspace):
    stranger = await workspace_create(title="Личное")
    await task_create(
        workspace_code=stranger.code, title="Чужая", type=TYPE_EXTENDED, context="панель"
    )

    assert await task_search_codes(workspace.code, "панель", in_brief=True) == []


async def test_stages_and_notes_of_a_stranger_do_not_leak_in(db, workspace):
    """A stage and an entry don't know their workspace — the join to the task holds the boundary.

    Separate from the previous test: there the boundary is checked on the task's own column, here
    on the join, and either can break without the other.
    """
    stranger = await workspace_create(title="Личное")
    alien = await task_create(
        workspace_code=stranger.code, title="Чужая", type=TYPE_EXTENDED
    )
    await stage_create(task_code=alien.code, title="Чужой шаг", body="редкое слово")
    await note_create(task_code=alien.code, type=NOTE_FACT, title="редкое слово")

    assert await task_search_codes(
        workspace.code, "редкое слово", in_plan=True, in_journal=True
    ) == []


async def test_deleted_tasks_are_not_filtered_out_here(db, workspace):
    """The endpoint's contract: deleted tasks stay in the answer — the intersection decides what
    to show.

    The caller holds the workspace's list and knows whether its trash is switched on. Filtering
    on this side would mean that with the trash on, deep search silently fails to find exactly
    what the person is looking at on screen right now.
    """
    row = await task_create(
        workspace_code=workspace.code,
        title="Удалённая",
        type=TYPE_EXTENDED,
        context="панель фильтров",
    )
    await task_delete(row.code)

    assert await task_search_codes(workspace.code, "панель", in_brief=True) == [row.code]


# ── endpoint ──────────────────────────────────────────────────────────────────


async def test_search_route_is_not_eaten_by_the_task_route(client):
    """``/tasks/search`` is declared above ``/tasks/{code}`` — otherwise it is the detail of a
    task called ``search``."""
    space = await workspace_create(title="Работа")
    row = await task_create(
        workspace_code=space.code,
        title="Задача",
        type=TYPE_EXTENDED,
        context="Панель фильтров",
    )

    response = await client.get(
        SEARCH, params={"workspace": space.code, "query": "ПАНЕЛЬ", "in_brief": True}
    )

    assert response.status_code == 200
    # The code goes out with its type — exactly the form it arrives in from the task list.
    assert response.json() == [f"TASK@{row.code}"]


async def test_search_route_refuses_an_unknown_workspace(client):
    response = await client.get(
        SEARCH, params={"workspace": "неттакого", "query": "панель", "in_brief": True}
    )

    assert response.status_code == 404


async def test_search_route_without_scopes_answers_empty(client):
    """No scope means an empty answer, not "the whole list": no haystack was given."""
    space = await workspace_create(title="Работа")
    await task_create(
        workspace_code=space.code, title="Задача", type=TYPE_EXTENDED, context="панель"
    )

    response = await client.get(SEARCH, params={"workspace": space.code, "query": "панель"})

    assert response.status_code == 200
    assert response.json() == []


async def test_search_route_takes_the_workspace_with_its_prefix(client):
    """The workspace code is accepted both bare and in the form every other endpoint returns."""
    space = await workspace_create(title="Работа")
    row = await task_create(
        workspace_code=space.code, title="Задача", type=TYPE_EXTENDED, body="глубокий текст"
    )

    response = await client.get(
        SEARCH,
        params={"workspace": f"WORKSPACE@{space.code}", "query": "глубокий", "in_plan": True},
    )

    assert response.json() == [f"TASK@{row.code}"]


# ── MCP ───────────────────────────────────────────────────────────────────────


async def test_mcp_list_finds_cyrillic_regardless_of_case(call, workspace):
    """The agent's search goes to the same query — and handles case the same way.

    Kept apart from the CRUD test on purpose: the fix lives in ``task_list_by_workspace``, but
    two surfaces use it, and the second has its own path to it.
    """
    await call("workspace_use", workspace_code=workspace.code)
    await task_create(workspace_code=workspace.code, title="Панель фильтров")

    found = await call("tasks_list", query="ПАНЕЛЬ")

    assert [row["title"] for row in found["tasks"]] == ["Панель фильтров"]
