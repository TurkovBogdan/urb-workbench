"""HTTP API of ``notes`` (/internal/notes): the document page reads a note and saves it whole."""

from __future__ import annotations

import pytest

from src.modules.notes.constants import BODY_MAX
from src.modules.notes.crud import note as note_crud

pytestmark = pytest.mark.db

BASE = "/internal/notes"


@pytest.mark.parametrize("form", ["NOTE@{}", "note@{lower}", "{lower}"])
async def test_get_takes_a_code_in_any_form_and_answers_upper_case(client, form):
    row = await note_crud.note_create(title="Схема", description="Когда", body="# Текст")

    response = await client.get(f"{BASE}/{form.format(row.code, lower=row.code.lower())}")

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["code"] == f"NOTE@{row.code}"
    assert (body["title"], body["description"], body["body"]) == ("Схема", "Когда", "# Текст")


async def test_get_shows_a_deleted_note_as_deleted(client):
    row = await note_crud.note_create(title="Схема")
    await note_crud.note_delete(row.code)

    body = (await client.get(f"{BASE}/NOTE@{row.code}")).json()

    assert body["deleted_at"] is not None


async def test_a_missing_note_is_404_and_a_foreign_code_is_400(client):
    missing = await client.get(f"{BASE}/NOTE@0000000000")
    foreign = await client.get(f"{BASE}/TASK@0000000000")

    assert (missing.status_code, missing.json()["code"]) == (404, "notes.note.not_found")
    assert foreign.status_code == 400
    assert "NOTE@ code is expected" in foreign.json()["error"]


async def test_put_saves_the_whole_document(client):
    row = await note_crud.note_create(title="Схема", description="Когда", body="старый")

    response = await client.put(
        f"{BASE}/note@{row.code.lower()}", json={"title": "  Схема v2  ", "body": "новый"}
    )

    assert response.status_code == 200, response.text
    assert response.json()["code"] == f"NOTE@{row.code}"
    stored = await note_crud.note_get(row.code)
    assert (stored.title, stored.description, stored.body) == ("Схема v2", "", "новый")


async def test_put_refuses_a_body_over_the_limit_and_keeps_the_note(client):
    row = await note_crud.note_create(title="Схема", body="старый")

    response = await client.put(
        f"{BASE}/NOTE@{row.code}", json={"title": "Схема", "body": "ж" * (BODY_MAX + 1)}
    )

    assert response.status_code == 422
    assert (await note_crud.note_get(row.code)).body == "старый"


async def test_put_refuses_an_unknown_field(client):
    row = await note_crud.note_create(title="Схема")

    response = await client.put(f"{BASE}/NOTE@{row.code}", json={"title": "Схема", "text": "х"})

    assert response.status_code == 422


async def test_put_on_a_deleted_note_is_409(client):
    row = await note_crud.note_create(title="Схема")
    await note_crud.note_delete(row.code)

    response = await client.put(f"{BASE}/NOTE@{row.code}", json={"title": "Новое"})

    assert (response.status_code, response.json()["code"]) == (409, "notes.note.deleted")
    assert (await note_crud.note_get(row.code, include_deleted=True)).title == "Схема"
