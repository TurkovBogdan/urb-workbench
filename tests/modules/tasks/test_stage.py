"""CRUD этапов плана: нумерация, отметки фаз и шлюз доказательства.

Шлюз здесь главный: закрыть этап без указателя на доказательство нельзя, и это единственная
проверка модуля, которая запрещает переход статуса. Всё остальное — арифметика номеров и отметки
времени, которые проставляет сам переход.
"""

from __future__ import annotations

import pytest

from src.modules.tasks.constants import (
    STATUS_CANCELED,
    STATUS_DONE,
    STATUS_IN_PROGRESS,
    STATUS_PLANNED,
    TYPE_EXTENDED,
    TYPE_STANDARD,
)
from src.modules.tasks.crud.stage import (
    stage_count_by_task_codes,
    stage_create,
    stage_delete,
    stage_get,
    stage_list_by_task,
    stage_update,
    stage_update_status,
)
from src.modules.tasks.crud.task import task_create, task_delete, task_update
from src.modules.tasks.errors import STAGE_EVIDENCE_REQUIRED, TaskRuleError

pytestmark = pytest.mark.db


@pytest.fixture
async def task(db, workspace):
    return await task_create(
        workspace_code=workspace.code, title="Перенести тарифы", type=TYPE_EXTENDED
    )


# ── номера ────────────────────────────────────────────────────────────────────


async def test_numbers_run_from_one_and_grow_down(task):
    first = await stage_create(task_code=task.code, title="Модели")
    second = await stage_create(task_code=task.code, title="Миграции")

    assert (first.number, second.number) == (1, 2)
    assert [row.number for row in await stage_list_by_task(task.code)] == [1, 2]


async def test_an_explicit_number_inserts_into_the_middle(task):
    await stage_create(task_code=task.code, title="Первый")
    await stage_create(task_code=task.code, title="Третий", number=3)

    inserted = await stage_create(task_code=task.code, title="Второй", number=2)

    assert inserted.number == 2
    assert [row.title for row in await stage_list_by_task(task.code)] == [
        "Первый",
        "Второй",
        "Третий",
    ]


async def test_a_taken_number_is_refused_by_name_not_by_the_index(task):
    """Занятый номер — обычный ход переработки плана, и отвечать на него SQL нельзя.

    Уникальность держит индекс, но упереться в него значит отдать наружу ``IntegrityError`` с
    куском INSERT: человеку шум, агенту текст, из которого нечем починиться. Слой проверяет сам
    и называет, кто номер держит.
    """
    first = await stage_create(task_code=task.code, title="Первый", number=1)

    with pytest.raises(ValueError, match=first.code):
        await stage_create(task_code=task.code, title="Дубль", number=1)


async def test_a_stage_may_keep_its_own_number(task):
    """Правка без переезда не должна отказывать, ссылаясь на саму переезжающую строку."""
    stage = await stage_create(task_code=task.code, title="Первый", number=1)

    assert (await stage_update(stage.code, number=1)).number == 1


async def test_numbers_are_counted_per_task(db, workspace):
    mine = await task_create(
        workspace_code=workspace.code, title="Моя", type=TYPE_EXTENDED
    )
    other = await task_create(
        workspace_code=workspace.code, title="Чужая", type=TYPE_EXTENDED
    )
    await stage_create(task_code=mine.code, title="Первый")

    assert (await stage_create(task_code=other.code, title="Первый")).number == 1


# ── принадлежность задаче ─────────────────────────────────────────────────────


async def test_a_stage_needs_a_live_task(db, workspace):
    task = await task_create(
        workspace_code=workspace.code, title="Удалённая", type=TYPE_EXTENDED
    )
    await task_delete(task.code)

    with pytest.raises(ValueError, match="does not exist"):
        await stage_create(task_code=task.code, title="Этап")


async def test_stages_belong_to_the_extended_task_only(db, workspace):
    """Этапы — единственное, чем расширенная отличается от стандартной.

    У стандартной план живёт прозой в теле, и этап там не показался бы нигде: полотно этапов
    интерфейс рисует только расширенной. Отказ обязан называть выход — и прозу, и повышение
    типа, — иначе агент упрётся в «нельзя» без понимания, что делать.
    """
    simple = await task_create(workspace_code=workspace.code, title="Записаться к врачу")
    standard = await task_create(
        workspace_code=workspace.code, title="Поправить форму", type=TYPE_STANDARD
    )

    for task in (simple, standard):
        with pytest.raises(ValueError, match="stages belong to extended only"):
            await stage_create(task_code=task.code, title="Этап")


async def test_raising_the_type_is_how_a_task_gets_stages(db, workspace):
    """Повышение типа — штатный путь для работы, которая оказалась длиннее, чем думали."""
    task = await task_create(
        workspace_code=workspace.code, title="Поправить форму", type=TYPE_STANDARD
    )
    await task_update(task.code, type=TYPE_EXTENDED)

    assert (await stage_create(task_code=task.code, title="Этап")).number == 1


async def test_purging_the_task_takes_its_stages(db, workspace, task):
    stage = await stage_create(task_code=task.code, title="Модели")

    await task_delete(task.code, hard=True)

    assert await stage_get(stage.code) is None


# ── статусы и отметки ─────────────────────────────────────────────────────────


async def test_a_new_stage_is_planned(task):
    assert (await stage_create(task_code=task.code, title="Модели")).status == STATUS_PLANNED


async def test_work_stamps_the_start_once(task):
    stage = await stage_create(task_code=task.code, title="Модели")

    started = await stage_update_status(stage.code, STATUS_IN_PROGRESS)
    await stage_update(stage.code, evidence="pytest -q → 6 passed")
    done = await stage_update_status(stage.code, STATUS_DONE)

    assert started.started_at is not None
    assert done.started_at == started.started_at
    assert done.finished_at is not None


async def test_a_cancelled_stage_is_finished_too(task):
    """«Отменён» — тоже конец работы: иначе «закрытые» и «открытые» перестают покрывать план."""
    stage = await stage_create(task_code=task.code, title="Через вебхуки")

    cancelled = await stage_update_status(stage.code, STATUS_CANCELED)

    assert cancelled.finished_at is not None


# ── шлюз доказательства ───────────────────────────────────────────────────────


async def test_closing_without_evidence_is_refused_by_name(task):
    stage = await stage_create(task_code=task.code, title="Модели")

    with pytest.raises(TaskRuleError) as refusal:
        await stage_update_status(stage.code, STATUS_DONE)

    assert refusal.value.code == STAGE_EVIDENCE_REQUIRED
    assert (await stage_get(stage.code)).status == STATUS_PLANNED


async def test_any_other_status_needs_no_evidence(task):
    """Шлюз стоит только на закрытии: работа и отмена доказательства не требуют."""
    stage = await stage_create(task_code=task.code, title="Модели")

    assert (await stage_update_status(stage.code, STATUS_IN_PROGRESS)).status == STATUS_IN_PROGRESS


async def test_an_unknown_status_is_refused(task):
    stage = await stage_create(task_code=task.code, title="Модели")

    with pytest.raises(ValueError, match="Unknown stage status"):
        await stage_update_status(stage.code, "почти готово")


# ── правка и удаление ─────────────────────────────────────────────────────────


async def test_update_touches_only_the_named_fields(task):
    stage = await stage_create(task_code=task.code, title="Модели", description="о чём")

    updated = await stage_update(stage.code, evidence="src/models/stage.py")

    assert (updated.title, updated.description) == ("Модели", "о чём")
    assert updated.evidence == "src/models/stage.py"


async def test_overlong_stage_body_is_refused(task):
    with pytest.raises(ValueError, match="shorten it by"):
        await stage_create(task_code=task.code, title="Модели", body="x" * 8193)


async def test_delete_removes_the_row(task):
    stage = await stage_create(task_code=task.code, title="Модели")

    assert await stage_delete(stage.code) is True
    assert await stage_get(stage.code) is None
    assert await stage_delete(stage.code) is False


async def test_counter_groups_by_task(db, workspace, task):
    other = await task_create(
        workspace_code=workspace.code, title="Вторая", type=TYPE_EXTENDED
    )
    await stage_create(task_code=task.code, title="Первый")
    await stage_create(task_code=task.code, title="Второй")
    await stage_create(task_code=other.code, title="Один")

    counts = await stage_count_by_task_codes([task.code, other.code])

    assert counts == {task.code: 2, other.code: 1}
