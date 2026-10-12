"""The handler tests again, on PostgreSQL: the queries must answer the same on both providers.

The handlers lean on things the two databases do differently — a boolean built from
``IS NOT NULL`` (an integer on SQLite, a ``bool`` on PostgreSQL), ``enabled IS TRUE`` on a boolean
column, joins across three tables — and a green SQLite run proves none of them on PostgreSQL. The
tests are the same functions as in ``test_handlers.py``; only the marker differs, so the fixture
gives them a fresh PostgreSQL database (``TEST_PG_DSN``) instead of in-memory SQLite.
"""

from __future__ import annotations

import pytest

from tests.modules.core_lookup.test_handlers import (  # noqa: F401 — collected here under `heavy`
    db,
    registered,
    test_a_deleted_codex_takes_its_notes_along,
    test_a_miss_carries_its_reason_and_nothing_else,
    test_a_workspace_is_shown_whichever_one_the_person_works_in,
    test_a_workspace_nobody_has_narrows_everything_away_but_workspaces,
    test_every_type_answers_with_its_title_description_and_page,
    test_the_foreign_ones_are_seen_from_their_own_workspace,
    test_the_retired_group_word_still_resolves,
    test_the_sql_count_does_not_grow_with_the_batch,
    test_without_a_workspace_filter_nothing_is_narrowed,
)

pytestmark = pytest.mark.heavy
