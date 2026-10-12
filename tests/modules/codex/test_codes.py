"""``CODEX@`` codes at the boundary: the stored form, the prefix, case, and a foreign type."""

from __future__ import annotations

import re

import pytest

from src.modules.codex.codes import bare_code, new_code, strip_prefix, tagged
from src.modules.codex.constants import CODE_LEN, CODEX_CODE_PREFIX

pytestmark = pytest.mark.pure


def test_a_drawn_code_is_bare_upper_hex_of_the_module_width():
    assert re.fullmatch(rf"[0-9A-F]{{{CODE_LEN}}}", new_code())


@pytest.mark.parametrize("given", ["CODEX@24afda32ca", "codex@24AFDA32CA", "24afda32ca"])
def test_any_case_and_form_folds_to_the_stored_code(given):
    assert bare_code(given, CODEX_CODE_PREFIX) == "24AFDA32CA"


def test_a_foreign_type_is_refused_naming_both():
    with pytest.raises(ValueError, match="NOTE@ reference, but a CODEX@ code is expected"):
        bare_code("NOTE@24AFDA32CA", CODEX_CODE_PREFIX)


def test_the_boundary_round_trip():
    assert tagged(CODEX_CODE_PREFIX, "24AFDA32CA") == "CODEX@24AFDA32CA"
    assert strip_prefix(tagged(CODEX_CODE_PREFIX, "24AFDA32CA")) == "24AFDA32CA"
    assert tagged(CODEX_CODE_PREFIX, None) is None
