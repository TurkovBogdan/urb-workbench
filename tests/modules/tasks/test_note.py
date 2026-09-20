"""Журнал работы: предмет и разрешение, дописываемость и счёт открытых записей.

Два правила здесь несут вес. Первое: запись закрывается ОДИН раз — переписать разрешение задним
числом нельзя, иначе историю можно подогнать под результат. Второе: открытая запись — та, у
которой разрешение пусто, и именно на этом числе будет стоять шлюз сдачи; факт в него не входит,
он закрыт в момент записи.
"""

from __future__ import annotations

import pytest

from src.modules.tasks.constants import (
    NOTE_DECISION,
    NOTE_FACT,
    NOTE_FINDING,
    NOTE_REMARK,
    NOTE_TYPES_BLOCKING,
    TYPE_EXTENDED,
    TYPE_STANDARD,
)
from src.modules.tasks.crud.note import (
    note_create,
    note_delete,
    note_get,
    note_list_by_task,
    note_open_count_by_task_codes,
    note_resolve,
)
from src.modules.tasks.crud.stage import stage_create
from src.modules.tasks.crud.task import task_create, task_delete
from src.modules.tasks.errors import NOTE_ALREADY_RESOLVED, TaskRuleError

pytestmark = pytest.mark.db


@pytest.fixture
async def task(db, workspace):
    """Журнал начинается со ``standard`` — на нём и проверяем, чтобы не перепутать с этапами.

    Этапы живут только у расширенной, журнал у обеих. Возьми сюда расширенную — и половина
    файла молча перестала бы сторожить, что журнал стандартной вообще работает.
    """
    return await task_create(
        workspace_code=workspace.code, title="Перенести тарифы", type=TYPE_STANDARD
    )


@pytest.fixture
async def staged(db, workspace):
    """Расширенная задача — для тех немногих случаев, где записи нужен этап."""
    return await task_create(
        workspace_code=workspace.code, title="С этапами", type=TYPE_EXTENDED
    )


# ── заведение ─────────────────────────────────────────────────────────────────


async def test_entry_starts_open(task):
    note = await note_create(task_code=task.code, type=NOTE_DECISION, title="Взяли SSE")

    assert note.resolution == ""
    assert note.stage_code is None


async def test_a_fact_may_be_closed_at_once(task):
    """Факт ничего не ждёт: он и заводится уже закрытым."""
    note = await note_create(
        task_code=task.code, type=NOTE_FACT, title="Строк 1842", resolution="записано"
    )

    assert note.resolution == "записано"


async def test_an_unknown_type_is_refused(task):
    with pytest.raises(ValueError, match="Unknown note type"):
        await note_create(task_code=task.code, type="мысль", title="Что-то")


async def test_an_entry_needs_a_live_task(db, workspace):
    task = await task_create(
        workspace_code=workspace.code, title="Удалённая", type=TYPE_STANDARD
    )
    await task_delete(task.code)

    with pytest.raises(ValueError, match="does not exist"):
        await note_create(task_code=task.code, type=NOTE_DECISION, title="Решение")


async def test_a_simple_task_keeps_no_journal(db, workspace):
    """Журнал начинается со ``standard`` — как и этапы, и по той же причине."""
    task = await task_create(workspace_code=workspace.code, title="Записаться к врачу")

    with pytest.raises(ValueError, match="Raise its type first"):
        await note_create(task_code=task.code, type=NOTE_DECISION, title="Решение")


async def test_a_stage_from_another_task_is_refused(db, workspace, task):
    stranger = await task_create(
        workspace_code=workspace.code, title="Чужая", type=TYPE_EXTENDED
    )
    stage = await stage_create(task_code=stranger.code, title="Чужой этап")

    with pytest.raises(ValueError, match="belongs to task"):
        await note_create(
            task_code=task.code, type=NOTE_DECISION, title="Решение", stage_code=stage.code
        )


async def test_an_entry_can_point_at_its_own_stage(staged):
    task = staged
    stage = await stage_create(task_code=task.code, title="Модели")

    note = await note_create(
        task_code=task.code, type=NOTE_FINDING, title="N+1 рядом", stage_code=stage.code
    )

    assert note.stage_code == stage.code


# ── закрытие ──────────────────────────────────────────────────────────────────


async def test_resolution_closes_the_entry(task):
    note = await note_create(task_code=task.code, type=NOTE_REMARK, title="Проверь форму")

    closed = await note_resolve(note.code, "Проверил, починил обе")

    assert closed.resolution == "Проверил, починил обе"


async def test_a_closed_entry_is_not_rewritten(task):
    note = await note_create(task_code=task.code, type=NOTE_DECISION, title="Куда девать agent")
    await note_resolve(note.code, "в standard")

    with pytest.raises(TaskRuleError) as refusal:
        await note_resolve(note.code, "нет, в extended")

    assert refusal.value.code == NOTE_ALREADY_RESOLVED
    assert (await note_get(note.code)).resolution == "в standard"


async def test_an_empty_resolution_closes_nothing(task):
    note = await note_create(task_code=task.code, type=NOTE_DECISION, title="Решение")

    with pytest.raises(ValueError, match="cannot be empty"):
        await note_resolve(note.code, "   ")


async def test_resolving_a_missing_entry_reports_none(db):
    assert await note_resolve("0" * 10, "что-то") is None


# ── выдача ────────────────────────────────────────────────────────────────────


async def test_list_returns_the_whole_journal_of_the_task(db, workspace, task):
    """Лента выдаётся по времени появления; чужая задача в неё не подмешивается.

    Внутри ОДНОЙ секунды порядок задаёт добивка по коду, а код случаен, — поэтому две записи,
    заведённые подряд, здесь сравниваются как множество. Тот же предел у журнала и на экране:
    точный порядок соседей по одной секунде ничем не обещан.
    """
    stranger = await task_create(
        workspace_code=workspace.code, title="Чужая", type=TYPE_STANDARD
    )
    first = await note_create(task_code=task.code, type=NOTE_DECISION, title="Первое")
    second = await note_create(task_code=task.code, type=NOTE_FACT, title="Второе")
    await note_create(task_code=stranger.code, type=NOTE_DECISION, title="Чужое")

    rows = await note_list_by_task(task.code)

    assert {row.code for row in rows} == {first.code, second.code}


async def test_list_narrows_to_a_type_and_to_open_ones(task):
    await note_create(task_code=task.code, type=NOTE_FACT, title="Факт", resolution="записано")
    decision = await note_create(task_code=task.code, type=NOTE_DECISION, title="Решение")

    by_type = await note_list_by_task(task.code, type=NOTE_DECISION)
    open_only = await note_list_by_task(task.code, open_only=True)

    assert [row.code for row in by_type] == [decision.code]
    assert [row.code for row in open_only] == [decision.code]


async def test_open_count_skips_facts_and_closed_entries(db, workspace, task):
    other = await task_create(
        workspace_code=workspace.code, title="Вторая", type=TYPE_STANDARD
    )
    await note_create(task_code=task.code, type=NOTE_DECISION, title="Открытое")
    closed = await note_create(task_code=task.code, type=NOTE_REMARK, title="Замечание")
    await note_resolve(closed.code, "учёл")
    await note_create(task_code=task.code, type=NOTE_FACT, title="Факт")
    await note_create(task_code=other.code, type=NOTE_DECISION, title="Чужое")

    counts = await note_open_count_by_task_codes([task.code, other.code])

    assert counts == {task.code: 1, other.code: 1}


async def test_the_hand_over_gate_does_not_count_findings(task):
    """Находка адресована не исполнителю, и запирать ею сдачу значит запирать её навсегда.

    Снять находку может только человек: она про работу ВНЕ этой задачи. Посчитай мы её наравне
    с решением — первая же добросовестно записанная находка сделала бы сдачу недостижимой, и
    агент перестал бы их записывать. Поэтому у счётчика два режима.
    """
    await note_create(task_code=task.code, type=NOTE_FINDING, title="Чужой дефект рядом")

    shown = await note_open_count_by_task_codes([task.code])
    blocking = await note_open_count_by_task_codes(
        [task.code], types=NOTE_TYPES_BLOCKING
    )

    assert shown == {task.code: 1}
    assert blocking == {}


async def test_purging_the_task_takes_its_journal(db, workspace, task):
    note = await note_create(task_code=task.code, type=NOTE_DECISION, title="Решение")

    await task_delete(task.code, hard=True)

    assert await note_get(note.code) is None


async def test_delete_removes_one_entry(task):
    note = await note_create(task_code=task.code, type=NOTE_DECISION, title="Решение")

    assert await note_delete(note.code) is True
    assert await note_delete(note.code) is False
