"""The codex service: slug and title rules, soft deletion that frees the slug, a refused restore.

Every refusal is followed by a read that shows nothing was written.
"""

from __future__ import annotations

import pytest

from src.modules.codex.crud.codex import (
    codex_create,
    codex_delete,
    codex_get,
    codex_get_by_slug,
    codex_list,
    codex_restore,
    codex_update,
)

pytestmark = pytest.mark.db


async def test_a_codex_is_created_with_a_fresh_code_and_found_by_slug(db):
    row = await codex_create(slug="python", title="Python-бэкенд", body="Правила")

    assert len(row.code) == 10
    assert (await codex_get_by_slug("python")).code == row.code
    assert (row.description, row.body, row.sort) == ("", "Правила", 500)


async def test_a_bad_slug_is_refused_and_nothing_is_written(db):
    with pytest.raises(ValueError, match="only a-z"):
        await codex_create(slug="Python", title="Python")

    assert await codex_list() == []


async def test_an_empty_title_is_refused(db):
    with pytest.raises(ValueError, match="title is empty"):
        await codex_create(slug="python", title="  ")


async def test_rules_over_the_limit_are_refused_with_the_numbers(db):
    with pytest.raises(ValueError, match="65537 characters long, the limit is 65536"):
        await codex_create(slug="python", title="Python", body="ж" * 65537)
    await codex_create(slug="python", title="Python", body="ж" * 65536)


async def test_a_taken_slug_is_refused_naming_its_holder(db):
    first = await codex_create(slug="python", title="Python")

    with pytest.raises(ValueError, match=f"taken by the codex 'Python' \\(CODEX@{first.code}\\)"):
        await codex_create(slug="python", title="Ещё Python")
    assert [c.code for c in await codex_list()] == [first.code]


async def test_renaming_to_a_taken_slug_is_refused_and_to_its_own_is_not(db):
    python = await codex_create(slug="python", title="Python")
    await codex_create(slug="vue", title="Vue")

    with pytest.raises(ValueError, match="taken by the codex 'Vue'"):
        await codex_update(python.code, slug="vue")
    assert (await codex_get(python.code)).slug == "python"

    renamed = await codex_update(python.code, slug="python", title="Python 3")
    assert (renamed.slug, renamed.title) == ("python", "Python 3")


async def test_a_deleted_codex_is_hidden_frees_its_slug_and_takes_no_edits(db):
    old = await codex_create(slug="python", title="Python")
    assert await codex_delete(old.code)

    assert await codex_get(old.code) is None
    assert await codex_get(old.code, include_deleted=True) is not None
    assert await codex_update(old.code, title="Правка") is None
    await codex_create(slug="python", title="Новый Python")


async def test_a_restore_is_refused_while_the_slug_is_taken(db):
    old = await codex_create(slug="python", title="Python")
    await codex_delete(old.code)
    newer = await codex_create(slug="python", title="Новый Python")

    with pytest.raises(ValueError, match="taken by the codex 'Новый Python'"):
        await codex_restore(old.code)
    assert await codex_get(old.code) is None

    await codex_update(newer.code, slug="python-new")
    assert await codex_restore(old.code)
    assert (await codex_get_by_slug("python")).code == old.code


async def test_restore_and_delete_of_what_is_not_there(db):
    live = await codex_create(slug="python", title="Python")

    assert not await codex_restore(live.code)
    assert not await codex_delete("0000000000")
