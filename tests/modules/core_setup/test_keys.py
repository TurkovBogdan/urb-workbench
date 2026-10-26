"""The environment settings form: how fields with a closed set of choices are entered."""

from __future__ import annotations

import pytest

from src.core.config import Config
from src.modules.core_setup.keys import FIELD_BY_KEY, UPDATE_BRANCHES

pytestmark = pytest.mark.pure


@pytest.mark.parametrize("key", ["DB_PROVIDER", "UPDATE_BRANCH"])
def test_closed_choices_are_entered_by_selection(key: str):
    """`choice` is a VSelect on the page; `str` would mean free input where there are 2 options."""
    assert FIELD_BY_KEY[key].type == "choice"
    assert FIELD_BY_KEY[key].choices


def test_vite_port_is_shown_only_in_developer_mode():
    """The form compares strings, and a switch writes `String(true)` — so the condition is "true"."""
    condition = FIELD_BY_KEY["SERVER_VITE_PORT"].visible_when

    assert condition is not None
    assert (condition.key, condition.equals) == ("APP_DEV_MODE", "true")
    assert FIELD_BY_KEY["APP_DEV_MODE"].type == "bool"


def test_update_branch_offers_the_lines_the_project_keeps():
    """The branch goes into git args; a typo in it surfaces only after the install is stopped."""
    assert FIELD_BY_KEY["UPDATE_BRANCH"].choices == UPDATE_BRANCHES
    assert set(UPDATE_BRANCHES) == {"main", "dev"}


def test_the_count_of_update_copies_is_a_number_kept_ten_by_default():
    """The form's key is the Config field: `.env` is topped up with the Config default."""
    assert FIELD_BY_KEY["UPDATE_KEEP_BACKUPS"].type == "int"
    assert Config.model_fields["update_keep_backups"].default == 10
