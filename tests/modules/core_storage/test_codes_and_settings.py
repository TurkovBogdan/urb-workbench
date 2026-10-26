"""File codes and the module settings — the two small things every service leans on."""

from __future__ import annotations

from datetime import timedelta

import pytest

from src.modules.core_storage import settings
from src.modules.core_storage.codes import new_code, normalize_code
from src.modules.core_storage.constants import CODE_LEN
from src.modules.core_storage.errors import FileNotFound

from .conftest import Settings

pytestmark = pytest.mark.pure


def test_a_new_code_is_ten_upper_hex():
    code = new_code()
    assert len(code) == CODE_LEN and code == code.upper()
    int(code, 16)


def test_an_incoming_code_is_trimmed_and_upper_cased():
    assert normalize_code(" 3f9a0c21be ") == "3F9A0C21BE"


@pytest.mark.parametrize(
    "value", ["", "3F9A0C21B", "3F9A0C21BEE", "3F9A0C21BZ", "FILE@3F9A0C21BE", None, 3]
)
def test_a_malformed_code_names_no_file(value):
    """A typo in a code is the commonest miss: the caller gets the same refusal as for a code
    nobody registered, not a ``ValueError`` it has no reason to catch."""
    with pytest.raises(FileNotFound):
        normalize_code(value)


def test_defaults_apply_before_the_settings_arrive():
    assert settings.cleanup_after() == timedelta(hours=48)
    assert settings.cleanup_limit() == 0
    assert settings.max_file_size() == 128 * 1024 * 1024


def test_the_current_settings_store_is_read_at_use():
    settings.set_current(Settings(cleanup_after_hours=2, cleanup_limit=5, max_file_size_mb=1))
    assert settings.cleanup_after() == timedelta(hours=2)
    assert settings.cleanup_limit() == 5
    assert settings.max_file_size() == 1024 * 1024


def test_the_schema_defaults_match_the_decisions():
    defaults = {field.key: field.default() for field in settings.SETTINGS_SCHEMA}
    assert defaults == {"cleanup_after_hours": 48, "cleanup_limit": 0, "max_file_size_mb": 128}
