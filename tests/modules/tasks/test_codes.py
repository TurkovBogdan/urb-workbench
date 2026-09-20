"""Кодек кодов ``tasks``: надевание и снятие префикса + отказ коду чужого типа.

Префикс — презентация, в базе его нет, поэтому кодек обязан быть идемпотентным на голом коде:
внутренние значения проходят через ту же границу, что и пришедшие снаружи.
"""

from __future__ import annotations

import json

import pytest
from pydantic import BaseModel

from src.modules.tasks.codes import (
    bare_code,
    code_prefix,
    new_code,
    prefixed,
    strip_prefix,
    tagged,
)
from src.modules.tasks.constants import (
    GROUP_CODE_PREFIX,
    CODE_LEN,
    TASK_CODE_PREFIX,
)
# Чужое тип-слово: коды пространства ходят через наши же границы (``workspace`` в параметрах ручек),
# и разбирать их модуль обязан по константе владельца, а не по своей копии.
from src.modules.workspace.constants import WORKSPACE_CODE_PREFIX

BARE = "a" * CODE_LEN


@pytest.mark.pure
def test_new_code_is_a_bare_hex_of_the_module_length():
    code = new_code()

    assert len(code) == CODE_LEN
    assert all(c in "0123456789abcdef" for c in code)
    assert new_code() != code


@pytest.mark.pure
def test_tagged_puts_the_prefix_on_and_strip_takes_it_off():
    assert tagged(TASK_CODE_PREFIX, BARE) == f"TASK@{BARE}"
    assert strip_prefix(f"TASK@{BARE}") == BARE
    assert tagged(TASK_CODE_PREFIX, None) is None


@pytest.mark.pure
def test_strip_prefix_is_idempotent_on_a_bare_code():
    """Внутреннее значение проходит границу столько раз, сколько нужно, и не портится."""
    assert strip_prefix(BARE) == BARE
    assert strip_prefix(strip_prefix(f"AREA@{BARE}")) == BARE


@pytest.mark.pure
def test_code_prefix_names_the_type_and_is_empty_for_a_bare_code():
    assert code_prefix(f"WORKSPACE@{BARE}") == WORKSPACE_CODE_PREFIX
    assert code_prefix(BARE) == ""


@pytest.mark.pure
@pytest.mark.parametrize("value", [f"TASK@{BARE}", BARE, "", None])
def test_bare_code_accepts_its_own_prefix_and_the_bare_form(value):
    expected = BARE if value else value

    assert bare_code(value, TASK_CODE_PREFIX) == expected


@pytest.mark.pure
def test_bare_code_refuses_a_foreign_prefix_by_naming_both_types():
    """Чужой код — перепутанный аргумент, а не пропавшая строка; отказ обязан это сказать."""
    with pytest.raises(ValueError, match="GROUP@ reference"):
        bare_code(f"{GROUP_CODE_PREFIX}@{BARE}", TASK_CODE_PREFIX)


@pytest.mark.pure
def test_prefixed_field_serialises_with_the_prefix_only_in_json():
    class Row(BaseModel):
        code: prefixed(TASK_CODE_PREFIX)

    row = Row(code=BARE)

    assert row.model_dump() == {"code": BARE}
    assert json.loads(row.model_dump_json()) == {"code": f"TASK@{BARE}"}
