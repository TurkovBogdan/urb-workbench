"""The work journal: subject and resolution, append-only, and the count of open entries.

Two rules carry the weight here. First: an entry is closed ONCE — the resolution cannot be
rewritten after the fact, or history could be fitted to the result. Second: an open entry is one
whose resolution is empty, and this very number is what the hand-in gate will stand on; a fact
does not count, it is closed the moment it is written.
"""

from __future__ import annotations

import pytest

from src.modules.tasks.constants import (
    JOURNAL_DECISION,
    JOURNAL_FACT,
    JOURNAL_FINDING,
    JOURNAL_REMARK,
    JOURNAL_TYPES_BLOCKING,
    TYPE_EXTENDED,
    TYPE_STANDARD,
)
from src.modules.tasks.crud.journal import (
    journal_create,
    journal_delete,
    journal_get,
    journal_list_by_task,
    journal_open_count_by_task_codes,
    journal_resolve,
)
from src.modules.tasks.crud.stage import stage_create
from src.modules.tasks.crud.task import task_create, task_delete
from src.modules.tasks.errors import JOURNAL_ALREADY_RESOLVED, TaskRuleError

pytestmark = pytest.mark.db


@pytest.fixture
async def task(db, workspace):
    """The journal starts at ``standard`` — so that is what we test on, not to mix it up with
    stages.

    Stages exist only on an extended task, the journal on both. Use an extended one here and half
    the file would silently stop guarding that a standard task's journal works at all.
    """
    return await task_create(
        workspace_code=workspace.code, title="Перенести тарифы", type=TYPE_STANDARD
    )


@pytest.fixture
async def staged(db, workspace):
    """An extended task — for the few cases where an entry needs a stage."""
    return await task_create(
        workspace_code=workspace.code, title="С этапами", type=TYPE_EXTENDED
    )


# ── creation ──────────────────────────────────────────────────────────────────


async def test_entry_starts_open(task):
    entry = await journal_create(task_code=task.code, type=JOURNAL_DECISION, title="Взяли SSE")

    assert entry.resolution == ""
    assert entry.stage_code is None


async def test_a_fact_may_be_closed_at_once(task):
    """A fact waits for nothing: it is created already closed."""
    entry = await journal_create(
        task_code=task.code, type=JOURNAL_FACT, title="Строк 1842", resolution="записано"
    )

    assert entry.resolution == "записано"


async def test_an_unknown_type_is_refused(task):
    with pytest.raises(ValueError, match="Unknown journal entry type"):
        await journal_create(task_code=task.code, type="мысль", title="Что-то")


async def test_an_entry_needs_a_live_task(db, workspace):
    task = await task_create(
        workspace_code=workspace.code, title="Удалённая", type=TYPE_STANDARD
    )
    await task_delete(task.code)

    with pytest.raises(ValueError, match="does not exist"):
        await journal_create(task_code=task.code, type=JOURNAL_DECISION, title="Решение")


async def test_a_simple_task_keeps_no_journal(db, workspace):
    """The journal starts at ``standard`` — like stages, and for the same reason."""
    task = await task_create(workspace_code=workspace.code, title="Записаться к врачу")

    with pytest.raises(ValueError, match="Raise its type first"):
        await journal_create(task_code=task.code, type=JOURNAL_DECISION, title="Решение")


async def test_a_stage_from_another_task_is_refused(db, workspace, task):
    stranger = await task_create(
        workspace_code=workspace.code, title="Чужая", type=TYPE_EXTENDED
    )
    stage = await stage_create(task_code=stranger.code, title="Чужой этап")

    with pytest.raises(ValueError, match="belongs to task"):
        await journal_create(
            task_code=task.code, type=JOURNAL_DECISION, title="Решение", stage_code=stage.code
        )


async def test_an_entry_can_point_at_its_own_stage(staged):
    task = staged
    stage = await stage_create(task_code=task.code, title="Модели")

    entry = await journal_create(
        task_code=task.code, type=JOURNAL_FINDING, title="N+1 рядом", stage_code=stage.code
    )

    assert entry.stage_code == stage.code


# ── closing ───────────────────────────────────────────────────────────────────


async def test_resolution_closes_the_entry(task):
    entry = await journal_create(task_code=task.code, type=JOURNAL_REMARK, title="Проверь форму")

    closed = await journal_resolve(entry.code, "Проверил, починил обе")

    assert closed.resolution == "Проверил, починил обе"


async def test_a_closed_entry_is_not_rewritten(task):
    entry = await journal_create(task_code=task.code, type=JOURNAL_DECISION, title="Куда девать agent")
    await journal_resolve(entry.code, "в standard")

    with pytest.raises(TaskRuleError) as refusal:
        await journal_resolve(entry.code, "нет, в extended")

    assert refusal.value.code == JOURNAL_ALREADY_RESOLVED
    assert (await journal_get(entry.code)).resolution == "в standard"


async def test_an_empty_resolution_closes_nothing(task):
    entry = await journal_create(task_code=task.code, type=JOURNAL_DECISION, title="Решение")

    with pytest.raises(ValueError, match="cannot be empty"):
        await journal_resolve(entry.code, "   ")


async def test_resolving_a_missing_entry_reports_none(db):
    assert await journal_resolve("0" * 10, "что-то") is None


# ── listing ───────────────────────────────────────────────────────────────────


async def test_list_returns_the_whole_journal_of_the_task(db, workspace, task):
    """The feed comes in order of creation; another task's entries are not mixed in.

    Within ONE second the order falls back to the code as a tiebreaker, and the code is random —
    so two entries created back to back are compared here as a set. The journal on screen has the
    same limit: the exact order of neighbours within one second is not promised by anything.
    """
    stranger = await task_create(
        workspace_code=workspace.code, title="Чужая", type=TYPE_STANDARD
    )
    first = await journal_create(task_code=task.code, type=JOURNAL_DECISION, title="Первое")
    second = await journal_create(task_code=task.code, type=JOURNAL_FACT, title="Второе")
    await journal_create(task_code=stranger.code, type=JOURNAL_DECISION, title="Чужое")

    rows = await journal_list_by_task(task.code)

    assert {row.code for row in rows} == {first.code, second.code}


async def test_list_narrows_to_a_type_and_to_open_ones(task):
    await journal_create(task_code=task.code, type=JOURNAL_FACT, title="Факт", resolution="записано")
    decision = await journal_create(task_code=task.code, type=JOURNAL_DECISION, title="Решение")

    by_type = await journal_list_by_task(task.code, type=JOURNAL_DECISION)
    open_only = await journal_list_by_task(task.code, open_only=True)

    assert [row.code for row in by_type] == [decision.code]
    assert [row.code for row in open_only] == [decision.code]


async def test_open_count_skips_facts_and_closed_entries(db, workspace, task):
    other = await task_create(
        workspace_code=workspace.code, title="Вторая", type=TYPE_STANDARD
    )
    await journal_create(task_code=task.code, type=JOURNAL_DECISION, title="Открытое")
    closed = await journal_create(task_code=task.code, type=JOURNAL_REMARK, title="Замечание")
    await journal_resolve(closed.code, "учёл")
    await journal_create(task_code=task.code, type=JOURNAL_FACT, title="Факт")
    await journal_create(task_code=other.code, type=JOURNAL_DECISION, title="Чужое")

    counts = await journal_open_count_by_task_codes([task.code, other.code])

    assert counts == {task.code: 1, other.code: 1}


async def test_the_hand_over_gate_does_not_count_findings(task):
    """A finding is not addressed to the executor, and locking hand-in on it locks it for good.

    Only the person can clear a finding: it is about work OUTSIDE this task. Were we to count it
    on a par with a decision, the very first honestly recorded finding would make hand-in
    unreachable, and the agent would stop recording them. Hence the counter's two modes.
    """
    await journal_create(task_code=task.code, type=JOURNAL_FINDING, title="Чужой дефект рядом")

    shown = await journal_open_count_by_task_codes([task.code])
    blocking = await journal_open_count_by_task_codes(
        [task.code], types=JOURNAL_TYPES_BLOCKING
    )

    assert shown == {task.code: 1}
    assert blocking == {}


async def test_purging_the_task_takes_its_journal(db, workspace, task):
    entry = await journal_create(task_code=task.code, type=JOURNAL_DECISION, title="Решение")

    await task_delete(task.code, hard=True)

    assert await journal_get(entry.code) is None


async def test_delete_removes_one_entry(task):
    entry = await journal_create(task_code=task.code, type=JOURNAL_DECISION, title="Решение")

    assert await journal_delete(entry.code) is True
    assert await journal_delete(entry.code) is False
