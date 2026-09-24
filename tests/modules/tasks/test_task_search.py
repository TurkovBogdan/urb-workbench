"""Поиск по задачам: регистр кириллицы и глубина по областям.

Две разные поверхности одного вопроса «где искать». Заголовок и цель ищет ``query`` у списка —
их видно в каждой строке. Тела (постановка, план с этапами, журнал) ищет ``task_search_codes``,
и только по явно названным областям: тихий поиск по восьмикилобайтным телам возвращает
совпадения, по которым не понять, та ли это задача.

Регистр проверяется КИРИЛЛИЦЕЙ намеренно: ``lower()`` в SQLite складывает только ASCII, и
сравнение, оставленное в SQL, молча разошлось бы с PostgreSQL — на латинице такой тест зелёный
на обоих.
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


# ── заголовок и цель ──────────────────────────────────────────────────────────


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
    """Список ищет только по строке списка: совпадение в плане его выдачу не расширяет."""
    await task_create(
        workspace_code=workspace.code,
        title="Панель фильтров",
        type=TYPE_EXTENDED,
        body="Ставлю SearchField первым в ряду",
    )

    assert await task_list_by_workspace(workspace.code, query="SearchField") == []


# ── глубина по областям ───────────────────────────────────────────────────────


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
    """Постановка — это четыре поля, и заголовок с целью в область не входят."""
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
    """План — это тело задачи и тела её этапов: шаг работы описан там, а не в карточке."""
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
    """Доказательство — такой же текст этапа, как и его тело: по нему ищут «чем это закрыли»."""
    row = await task_create(
        workspace_code=workspace.code, title="С доказательством", type=TYPE_EXTENDED
    )
    stage = await stage_create(task_code=row.code, title="Шаг")
    await stage_update(stage.code, evidence="pytest --core → 1491 passed")

    assert await task_search_codes(workspace.code, "1491 PASSED", in_plan=True) == [row.code]


async def test_journal_scope_reads_the_resolution(db, workspace):
    """Разрешение записи — половина её смысла: «чем кончилось» ищут наравне с «о чём было»."""
    row = await task_create(
        workspace_code=workspace.code, title="С решением", type=TYPE_EXTENDED
    )
    note = await note_create(
        task_code=row.code, type=NOTE_DECISION, title="Куда класть области поиска"
    )
    await note_resolve(note.code, "Переходник живёт в search.ts")

    assert await task_search_codes(workspace.code, "ПЕРЕХОДНИК", in_journal=True) == [row.code]


async def test_scopes_combine_and_a_task_comes_back_once(db, workspace):
    """Области складываются, а не пересекаются; совпавшая дважды задача приходит одной строкой."""
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
    """Этап и запись своего пространства не знают — границу держит join к задаче.

    Отдельно от предыдущего теста: там граница проверяется на колонке самой задачи, здесь — на
    соединении, и сломаться они могут по одному.
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
    """Контракт ручки: удалённые остаются в ответе — что показывать, решает пересечение.

    Спрашивающий держит список пространства и знает, включена ли у него корзина. Отсев на этой
    стороне означал бы, что при включённой корзине глубокий поиск молча не находит ровно то, что
    человек прямо сейчас видит на экране.
    """
    row = await task_create(
        workspace_code=workspace.code,
        title="Удалённая",
        type=TYPE_EXTENDED,
        context="панель фильтров",
    )
    await task_delete(row.code)

    assert await task_search_codes(workspace.code, "панель", in_brief=True) == [row.code]


# ── ручка ─────────────────────────────────────────────────────────────────────


async def test_search_route_is_not_eaten_by_the_task_route(client):
    """``/tasks/search`` объявлен выше ``/tasks/{code}`` — иначе это деталь задачи ``search``."""
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
    # Код уезжает с типом — ровно в той форме, в какой он приходит в списке задач.
    assert response.json() == [f"TASK@{row.code}"]


async def test_search_route_refuses_an_unknown_workspace(client):
    response = await client.get(
        SEARCH, params={"workspace": "неттакого", "query": "панель", "in_brief": True}
    )

    assert response.status_code == 404


async def test_search_route_without_scopes_answers_empty(client):
    """Ни одной области — пустой ответ, а не «весь список»: стога не задали."""
    space = await workspace_create(title="Работа")
    await task_create(
        workspace_code=space.code, title="Задача", type=TYPE_EXTENDED, context="панель"
    )

    response = await client.get(SEARCH, params={"workspace": space.code, "query": "панель"})

    assert response.status_code == 200
    assert response.json() == []


async def test_search_route_takes_the_workspace_with_its_prefix(client):
    """Код пространства принимается и голым, и в том виде, в каком его отдают все остальные ручки."""
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
    """Поиск агента ходит в ту же выборку — и ловит регистр так же.

    Стоит отдельно от CRUD-теста намеренно: починка живёт в ``task_list_by_workspace``, а
    пользуются ею две поверхности, и у второй свой путь до неё.
    """
    await call("workspace_use", workspace_code=workspace.code)
    await task_create(workspace_code=workspace.code, title="Панель фильтров")

    found = await call("tasks_list", query="ПАНЕЛЬ")

    assert [row["title"] for row in found["tasks"]] == ["Панель фильтров"]
