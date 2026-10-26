"""The storage tests again, on PostgreSQL: a green SQLite run proves none of what differs.

SQLite stores a value longer than its ``VARCHAR`` and enforces foreign keys only when told to;
PostgreSQL refuses the first and always enforces the second. ``ON CONFLICT … RETURNING`` is built
by a different dialect module on each. The tests are the same functions as in the ``db`` files;
only the marker differs, so the fixture gives them a fresh PostgreSQL database (``TEST_PG_DSN``).
"""

from __future__ import annotations

import pytest
from sqlalchemy import insert
from sqlalchemy.exc import DBAPIError

from src.core.database import get_engine, write_scope
from src.modules.core_storage.constants import (
    EXTENSION_MAX,
    ORIGINAL_FILENAME_MAX,
    OWNER_ID_MAX,
    OWNER_KEY_MAX,
    OWNER_TYPE_MAX,
)
from src.modules.core_storage.models import CoreStorageFileOwner
from src.modules.core_storage.dto import Owner
from src.modules.core_storage.services.registration import file_register_bytes
from tests.modules.core_storage.conftest import owners_of
from tests.modules.core_storage.test_cleanup import (  # noqa: F401 — collected here under `heavy`
    test_a_file_past_the_term_goes_with_its_bytes,
    test_a_live_owner_keeps_a_marked_file_and_clears_the_mark,
    test_the_limit_bounds_one_run_and_zero_means_all,
)
from tests.modules.core_storage.test_failure_paths import (  # noqa: F401
    test_a_code_taken_by_a_soft_deleted_file_is_chosen_again,
    test_a_refusal_other_than_a_taken_code_goes_out_as_is,
    test_losing_the_race_for_the_content_joins_the_winner,
    test_losing_the_race_revives_a_marked_winner,
)
from tests.modules.core_storage.test_files import (  # noqa: F401
    test_get_many_skips_codes_without_a_file,
    test_the_manager_deletes_the_file_and_all_its_owners_softly,
)
from tests.modules.core_storage.test_original_names import (  # noqa: F401
    test_a_name_at_the_width_is_stored_whole,
    test_a_name_the_storage_cannot_keep_is_refused_and_nothing_is_written,
    test_attach_copies_the_earliest_name_there_is_skipping_rows_without_one,
    test_attach_writes_a_given_name_and_copies_the_files_name_otherwise,
    test_taking_a_place_again_keeps_the_name_unless_a_new_one_is_given,
    test_the_same_bytes_keep_each_owners_own_name,
)
from tests.modules.core_storage.test_holders import (  # noqa: F401
    test_a_category_outside_the_list__the_check_holds,
    test_a_file_with_an_owner_row_cannot_be_deleted__the_fk_restrict_holds,
    test_an_owner_of_a_missing_file_cannot_be_written__the_fk_holds,
    test_the_same_bytes_twice_in_one_store__the_unique_key_holds,
)
from tests.modules.core_storage.test_ownership import (  # noqa: F401
    test_an_entity_is_released_from_every_file_and_place,
    test_one_entity_holds_a_file_in_two_places,
    test_taking_a_marked_file_back_revives_it_and_the_owner,
    test_the_last_owner_leaving_marks_the_file,
)
from tests.modules.core_storage.test_registration import (  # noqa: F401
    test_a_failed_move_takes_the_row_back,
    test_a_taken_code_is_chosen_again,
    test_registering_a_soft_deleted_file_revives_it,
    test_the_same_bytes_in_another_store_are_a_second_file,
    test_the_three_inputs_give_one_file,
)

pytestmark = pytest.mark.heavy


async def test_this_tier_really_runs_on_postgres(db):
    """Positive control for every test collected here: a skipped DSN must not pass as SQLite."""
    assert get_engine().dialect.name == "postgresql"


async def test_an_owner_at_every_width_limit_is_stored_whole_on_postgres(db):
    owner = Owner("t" * OWNER_TYPE_MAX, "и" * OWNER_ID_MAX, "к" * OWNER_KEY_MAX)
    stored = await file_register_bytes(b"wide", store="public", owner=owner)
    assert await owners_of(stored.code) == [owner]


async def test_postgres_refuses_a_value_wider_than_its_column__why_owner_checks_widths(db):
    stored = await file_register_bytes(b"x", store="public", owner=Owner("task", "1"))
    with pytest.raises(DBAPIError):
        async with write_scope() as s:
            await s.execute(
                insert(CoreStorageFileOwner).values(
                    file_code=stored.code,
                    owner_type="task",
                    owner_id="i" * (OWNER_ID_MAX + 1),
                    owner_key="",
                )
            )


@pytest.mark.parametrize(
    "wide",
    [
        {"original_filename": "n" * (ORIGINAL_FILENAME_MAX + 1)},
        {"original_extension": "." + "x" * EXTENSION_MAX},
    ],
    ids=["filename", "extension"],
)
async def test_postgres_refuses_a_name_wider_than_its_column__why_the_name_is_checked(db, wide):
    stored = await file_register_bytes(b"x", store="public", owner=Owner("task", "1"))
    with pytest.raises(DBAPIError):
        async with write_scope() as s:
            await s.execute(
                insert(CoreStorageFileOwner).values(
                    file_code=stored.code, owner_type="note", owner_id="1", owner_key="", **wide
                )
            )
