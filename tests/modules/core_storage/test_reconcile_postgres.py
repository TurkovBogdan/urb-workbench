"""The reconciliation again, on PostgreSQL: the removal takes the row with a real
``SELECT … FOR UPDATE`` there, and the dedup's self-healing runs under it.

The same functions as in ``test_reconcile.py``; the marker gives them a fresh PostgreSQL database
(``TEST_PG_DSN``).
"""

from __future__ import annotations

import pytest

from src.core.database import get_engine
from tests.modules.core_storage.test_reconcile import (  # noqa: F401 — collected here under `heavy`
    test_a_held_file_without_bytes_is_reported_and_kept,
    test_a_marked_file_without_bytes_is_left_to_the_cleanup,
    test_a_row_that_appears_before_the_removal_keeps_its_bytes,
    test_a_row_younger_than_the_term_is_not_looked_for,
    test_bytes_the_cleanup_left_after_its_commit_are_removed,
    test_bytes_without_a_row_past_the_term_are_removed_with_their_folders,
    test_the_scheduled_run_removes_nothing_when_the_leftovers_are_too_many,
    test_the_task_reports_into_its_run_and_removes_few_leftovers,
    test_uploading_the_same_content_brings_lost_bytes_back,
)

pytestmark = pytest.mark.heavy


async def test_the_dialect_is_postgresql(db):
    assert get_engine().dialect.name == "postgresql"
