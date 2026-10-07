"""The ``tasks`` code codec: adding and stripping the prefix + refusing a code of another type.

The prefix is presentation, the database never holds it, so the codec must be idempotent on a bare
code: internal values pass through the same boundary as the ones arriving from outside. Codes are
upper case, and the codec folds whatever case comes in.
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
# A foreign type word: workspace codes pass through our own boundaries (``workspace`` in endpoint
# params), and the module must parse them by the owner's constant, not by a copy of its own.
from src.modules.workspace.constants import WORKSPACE_CODE_PREFIX

BARE = "A" * CODE_LEN


@pytest.mark.pure
def test_new_code_is_an_upper_case_hex_of_the_module_length():
    code = new_code()

    assert len(code) == CODE_LEN
    assert all(c in "0123456789ABCDEF" for c in code)
    assert new_code() != code


@pytest.mark.pure
@pytest.mark.parametrize(
    "value", [f"TASK@{BARE.lower()}", f"task@{BARE}", f"Task@{BARE.lower()}", BARE.lower()]
)
def test_bare_code_folds_any_case_to_the_stored_upper_case(value):
    """A code from before the switch (a config, a link in a note) must still find its row."""
    assert bare_code(value, TASK_CODE_PREFIX) == BARE


@pytest.mark.pure
def test_strip_prefix_folds_case_too():
    assert strip_prefix(f"group@{BARE.lower()}") == BARE


@pytest.mark.pure
def test_a_foreign_prefix_is_refused_in_any_case():
    """Folding must not let a lower-case foreign type slip past the type check."""
    with pytest.raises(ValueError, match="TASKGROUP@ reference"):
        bare_code(f"taskgroup@{BARE}", TASK_CODE_PREFIX)


@pytest.mark.pure
def test_tagged_puts_the_prefix_on_and_strip_takes_it_off():
    assert tagged(TASK_CODE_PREFIX, BARE) == f"TASK@{BARE}"
    assert strip_prefix(f"TASK@{BARE}") == BARE
    assert tagged(TASK_CODE_PREFIX, None) is None


@pytest.mark.pure
def test_strip_prefix_is_idempotent_on_a_bare_code():
    """An internal value crosses the boundary as many times as needed and comes out intact."""
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
    """A foreign code is a mixed-up argument, not a missing row; the refusal must say so."""
    with pytest.raises(ValueError, match="TASKGROUP@ reference"):
        bare_code(f"{GROUP_CODE_PREFIX}@{BARE}", TASK_CODE_PREFIX)


@pytest.mark.pure
@pytest.mark.parametrize("value", [f"GROUP@{BARE}", f"group@{BARE.lower()}"])
def test_the_retired_group_prefix_reads_as_the_current_one(value):
    """``GROUP@`` codes are already quoted in bodies and journals; the rename must not orphan them."""
    assert code_prefix(value) == GROUP_CODE_PREFIX
    assert bare_code(value, GROUP_CODE_PREFIX) == BARE


@pytest.mark.pure
def test_the_retired_group_prefix_is_still_refused_where_a_task_is_expected():
    """The alias widens what a group code may look like, not what a task code may be."""
    with pytest.raises(ValueError, match="TASKGROUP@ reference"):
        bare_code(f"GROUP@{BARE}", TASK_CODE_PREFIX)


@pytest.mark.pure
@pytest.mark.parametrize("value", ["TASK@", f"TASK@TASK@{BARE}", f"@{BARE}@"])
def test_bare_code_refuses_a_prefix_with_no_single_code_after_it(value):
    """An empty tail means "unset" in CRUD: a truncated code silently moved the task to the root."""
    with pytest.raises(ValueError, match="is not a TASK@ code"):
        bare_code(value, TASK_CODE_PREFIX)


@pytest.mark.pure
def test_prefixed_field_serialises_with_the_prefix_only_in_json():
    class Row(BaseModel):
        code: prefixed(TASK_CODE_PREFIX)

    row = Row(code=BARE)

    assert row.model_dump() == {"code": BARE}
    assert json.loads(row.model_dump_json()) == {"code": f"TASK@{BARE}"}
