"""Ownership: who holds a file, and the mark when nobody does."""

from __future__ import annotations

from datetime import timedelta

import pytest

from src.core.utils.date import utc_now
from src.modules.core_storage.dto import HeldFile, Owner
from src.modules.core_storage.errors import FileNotFound
from src.modules.core_storage.services import files
from src.modules.core_storage.services.ownership import (
    file_attach,
    file_owners,
    file_owners_many,
    file_release,
    held_by_type,
    owner_release_everywhere,
)
from src.modules.core_storage.services.registration import file_register_bytes

from .conftest import back_date_owner, names_of, owners_of

pytestmark = pytest.mark.db

CONTEXT = Owner("task", "7DB4F6E0DE", "context")
CRITERIA = Owner("task", "7DB4F6E0DE", "criteria")
NOTE = Owner("note", "BD98065ED2")


async def _deleted_at(code: str):
    return (await files.file_get(code, include_deleted=True)).deleted_at


async def test_attach_adds_an_owner_once(db):
    stored = await file_register_bytes(b"x", store="public", owner=CONTEXT)
    await file_attach(stored.code, NOTE)
    await file_attach(stored.code, NOTE)
    assert await owners_of(stored.code) == [NOTE, CONTEXT]


async def test_one_entity_holds_a_file_in_two_places(db):
    stored = await file_register_bytes(b"x", store="public", owner=CONTEXT)
    await file_attach(stored.code, CRITERIA)

    await file_release(stored.code, CONTEXT)

    assert await _deleted_at(stored.code) is None
    assert await owners_of(stored.code) == [CRITERIA]


async def test_the_last_owner_leaving_marks_the_file(db):
    stored = await file_register_bytes(b"x", store="public", owner=CONTEXT)
    await file_release(stored.code, CONTEXT)

    assert await _deleted_at(stored.code) is not None
    assert await file_owners(stored.code) == []
    assert await owners_of(stored.code, include_deleted=True) == [CONTEXT]
    with pytest.raises(FileNotFound):
        await files.file_get(stored.code)


async def test_releasing_twice_changes_nothing_and_says_so(db):
    stored = await file_register_bytes(b"x", store="public", owner=CONTEXT)
    await file_attach(stored.code, NOTE)
    assert await file_release(stored.code, CONTEXT) is True
    assert await file_release(stored.code, CONTEXT) is False
    assert await _deleted_at(stored.code) is None


async def test_releasing_a_place_the_owner_never_held_is_reported_and_marks_nothing(db):
    """A consumer that got its key wrong must find out: a silent no-op would leave the file
    held forever by the place it meant to release."""
    stored = await file_register_bytes(b"x", store="public", owner=CONTEXT)

    assert await file_release(stored.code, CRITERIA) is False
    assert await file_release(stored.code, Owner("task", "0000000000", "context")) is False

    assert await _deleted_at(stored.code) is None
    assert await owners_of(stored.code) == [CONTEXT]


async def test_taking_a_marked_file_back_revives_it_and_the_owner(db):
    stored = await file_register_bytes(b"x", store="public", owner=CONTEXT)
    await file_release(stored.code, CONTEXT)

    await file_attach(stored.code.lower(), CONTEXT)

    assert await _deleted_at(stored.code) is None
    assert await owners_of(stored.code) == [CONTEXT]


async def test_an_entity_is_released_from_every_file_and_place(db):
    only_task = await file_register_bytes(b"only task", store="public", owner=CONTEXT)
    await file_attach(only_task.code, CRITERIA)
    shared = await file_register_bytes(b"shared", store="public", owner=CONTEXT)
    await file_attach(shared.code, NOTE)

    released = await owner_release_everywhere("task", "7DB4F6E0DE")

    assert released == 3
    assert await _deleted_at(only_task.code) is not None
    assert await _deleted_at(shared.code) is None
    assert await owners_of(shared.code) == [NOTE]


async def test_an_unknown_file_cannot_be_taken_or_released(db):
    with pytest.raises(FileNotFound):
        await file_attach("ABCDEF0123", NOTE)
    with pytest.raises(FileNotFound):
        await file_release("ABCDEF0123", NOTE)


async def test_owners_of_a_batch_are_read_per_file(db):
    first = await file_register_bytes(b"first", store="public", owner=CONTEXT, filename="a.md")
    await file_attach(first.code, NOTE, filename="b.md")
    second = await file_register_bytes(b"second", store="public", owner=NOTE)
    released = await file_register_bytes(b"released", store="public", owner=CRITERIA)
    await file_release(released.code, CRITERIA)

    many = await file_owners_many(
        [first.code, second.code.lower(), released.code, "ABCDEF0123", "not a code"]
    )

    assert {code: [place.owner for place in places] for code, places in many.items()} == {
        first.code: [NOTE, CONTEXT],
        second.code: [NOTE],
    }
    assert many[first.code] == await file_owners(first.code)
    with_released = await file_owners_many([released.code], include_deleted=True)
    assert [place.owner for place in with_released[released.code]] == [CRITERIA]
    assert await file_owners_many([]) == {}


async def test_held_by_type_lists_the_live_places_of_one_type_only(db):
    first = await file_register_bytes(b"one", store="public", owner=CONTEXT)
    await file_attach(first.code, CRITERIA)
    await file_attach(first.code, NOTE)
    released = await file_register_bytes(b"two", store="public", owner=CONTEXT)
    await file_release(released.code, CONTEXT)

    held = await held_by_type("task")

    assert held == [HeldFile(first.code, CONTEXT), HeldFile(first.code, CRITERIA)]
    assert await held_by_type("nobody") == []


async def test_held_by_type_leaves_out_the_places_taken_since_a_moment(db):
    """A reconciliation asks only for places older than its grace: an attach in flight in
    another process has taken its place a moment ago and has not written its binding yet."""
    old = await file_register_bytes(b"old", store="public", owner=CONTEXT)
    await back_date_owner(old.code, CONTEXT, utc_now() - timedelta(hours=1))
    await file_register_bytes(b"fresh", store="public", owner=CONTEXT)

    held = await held_by_type("task", taken_before=utc_now() - timedelta(minutes=10))

    assert held == [HeldFile(old.code, CONTEXT)]


@pytest.mark.parametrize("again", ["attach", "register"])
async def test_a_released_place_taken_again_counts_as_taken_now(db, again):
    stored = await file_register_bytes(b"x", store="public", owner=CONTEXT, filename="a.txt")
    await file_attach(stored.code, NOTE)
    await back_date_owner(stored.code, CONTEXT, utc_now() - timedelta(hours=1))
    await file_release(stored.code, CONTEXT)

    if again == "attach":
        await file_attach(stored.code, CONTEXT)
    else:
        await file_register_bytes(b"x", store="public", owner=CONTEXT)

    assert await held_by_type("task", taken_before=utc_now() - timedelta(minutes=10)) == []
    assert await held_by_type("task") == [HeldFile(stored.code, CONTEXT)]
    assert (await names_of(stored.code))[CONTEXT] == ("a", ".txt")
