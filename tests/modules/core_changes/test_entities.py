"""Объявления сущностей ленты изменений: проверка при регистрации."""

from __future__ import annotations

import pytest

from src.modules.core_changes.entities import (
    ChangeEntity,
    Code,
    clear_entities,
    entity_for_model,
    register_entity,
)
from src.modules.tasks.models import TasksStage, TasksTask

pytestmark = pytest.mark.pure


@pytest.fixture(autouse=True)
def _clean_registry():
    clear_entities()
    yield
    clear_entities()


def test_declared_model_is_found_by_its_class():
    entity = ChangeEntity("tasks.task", TasksTask, id=Code("code", "TASK"))
    register_entity(entity)
    assert entity_for_model(TasksTask) is entity
    assert entity_for_model(TasksStage) is None


def test_repeating_the_same_declaration_is_allowed():
    entity = ChangeEntity("tasks.task", TasksTask, id=Code("code", "TASK"))
    register_entity(entity)
    register_entity(entity)


def test_one_name_for_two_models_is_refused():
    register_entity(ChangeEntity("tasks.thing", TasksTask, id=Code("code")))
    with pytest.raises(ValueError, match="already declared"):
        register_entity(ChangeEntity("tasks.thing", TasksStage, id=Code("code")))


@pytest.mark.parametrize(
    "entity",
    [
        ChangeEntity("tasks.task", TasksTask, id=Code("no_such_column")),
        ChangeEntity("tasks.task", TasksTask, id=Code("code"), refs=(Code("parent"),)),
    ],
)
def test_missing_column_is_refused_at_registration(entity):
    with pytest.raises(ValueError, match="has no column"):
        register_entity(entity)


def test_code_renders_with_its_prefix():
    assert Code("code", "TASK").render("3f1a") == "TASK@3f1a"
    assert Code("code").render("3f1a") == "3f1a"
    assert Code("code", "TASK").render(None) is None
