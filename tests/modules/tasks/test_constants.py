"""Справочники значений и мягкое усечение текста — без БД.

Кортежи из ``constants.py`` — единственный источник для ORM-``CHECK``, миграции и валидации в
CRUD. Тесты сторожат их внутреннюю связность: дефолт обязан быть допустимым значением, а
терминальные статусы — подмножеством статусов.
"""

from __future__ import annotations

import pytest

from src.modules.tasks.constants import (
    ACTOR_KINDS,
    TASK_CREATED_BY_DEFAULT,
    TASK_PRIORITIES,
    TASK_PRIORITY_DEFAULT,
    TASK_PRIORITY_WEIGHTS,
    TASK_STATUS_DEFAULT,
    TASK_STATUSES,
    TASK_STATUSES_TERMINAL,
    TASK_TYPE_DEFAULT,
    TASK_TYPES,
    TITLE_MAX,
    sql_in,
)
from src.modules.tasks.text import clip


@pytest.mark.pure
@pytest.mark.parametrize(
    ("default", "allowed"),
    [
        (TASK_STATUS_DEFAULT, TASK_STATUSES),
        (TASK_PRIORITY_DEFAULT, TASK_PRIORITIES),
        (TASK_TYPE_DEFAULT, TASK_TYPES),
        (TASK_CREATED_BY_DEFAULT, ACTOR_KINDS),
    ],
)
def test_every_default_is_a_member_of_its_dictionary(default, allowed):
    assert default in allowed


@pytest.mark.pure
def test_terminal_statuses_are_a_subset_of_the_statuses():
    assert set(TASK_STATUSES_TERMINAL) <= set(TASK_STATUSES)


@pytest.mark.pure
def test_every_priority_has_a_sorting_weight_and_the_weights_are_distinct():
    """Вес нужен каждому значению: приоритет без веса уехал бы в сортировке в ``else_``."""
    assert set(TASK_PRIORITY_WEIGHTS) == set(TASK_PRIORITIES)
    assert len(set(TASK_PRIORITY_WEIGHTS.values())) == len(TASK_PRIORITIES)
    assert TASK_PRIORITY_WEIGHTS["burning"] < TASK_PRIORITY_WEIGHTS["frozen"]


@pytest.mark.pure
def test_sql_in_quotes_every_value_for_a_check_constraint():
    assert sql_in(("a", "b")) == "'a', 'b'"


@pytest.mark.pure
def test_clip_cuts_cyrillic_by_code_points_not_bytes():
    """Кириллица в UTF-8 — два байта на символ: срез по байтам разрубил бы символ пополам."""
    clipped = clip("я" * (TITLE_MAX + 50), TITLE_MAX)

    assert len(clipped) == TITLE_MAX
    assert clipped == "я" * TITLE_MAX


@pytest.mark.pure
def test_clip_turns_none_into_an_empty_string():
    assert clip(None, TITLE_MAX) == ""
