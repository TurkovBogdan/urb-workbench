"""HTTP API of a codex note's files: the list, re-titling, the order, detaching.

The files here are attached through the service, as the uploads do; the person's upload is
``test_upload_holder.py``. A codex code is refused by name: a codex holds no files. Every
refusal is checked by the state after it.
"""

from __future__ import annotations

import pytest

from src.modules.codex.constants import FILE_TITLE_MAX
from src.modules.codex.crud import codex as codex_crud
from src.modules.codex.crud import file as file_crud
from src.modules.codex.crud import note as note_crud
from src.modules.core_storage.services.files import file_delete
from src.modules.core_storage.services.ownership import file_owners
from tests.modules.codex.file_support import codex_file_attach_bytes

pytestmark = pytest.mark.db

NOTES = "/internal/codex/notes"
PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64


@pytest.fixture
async def codex(client, storage):
    return await codex_crud.codex_create(segment="python", title="Python")


@pytest.fixture
async def note(codex):
    return await note_crud.note_create(parent_code=codex.code, segment="test", title="Тесты")


async def _order(note_code: str) -> list[str]:
    return [row.file_code for row in await file_crud.codex_file_list(note_code)]


async def test_the_list_carries_the_binding_and_what_the_storage_knows(client, note):
    image = await codex_file_attach_bytes(
        note.code, PNG, filename="Схема.png", title="Поток", description="Как идёт запрос"
    )
    text = await codex_file_attach_bytes(note.code, b"x", filename="x.md")

    response = await client.get(f"{NOTES}/codex@{note.code.lower()}/files")

    assert response.status_code == 200, response.text
    rows = response.json()
    assert [row["code"] for row in rows] == [f"FILE@{image.file_code}", f"FILE@{text.file_code}"]
    assert {key: rows[0][key] for key in (
        "note_code", "title", "description", "original_filename", "original_extension",
        "mime", "type", "size", "sort",
    )} == {
        "note_code": f"CODEX@{note.code}",
        "title": "Поток",
        "description": "Как идёт запрос",
        "original_filename": "Схема",
        "original_extension": ".png",
        "mime": "image/png",
        "type": "image",
        "size": len(PNG),
        "sort": image.sort,
    }


async def test_a_codex_code_is_refused_by_name(client, codex):
    response = await client.get(f"{NOTES}/{codex.code}/files")

    assert response.status_code == 400
    assert response.json()["code"] == "codex.file.holder_is_codex"


async def test_an_unknown_note_is_404(client, codex):
    response = await client.get(f"{NOTES}/0000000000/files")

    assert response.status_code == 404
    assert response.json()["code"] == "codex.note.not_found"


async def test_patch_order_and_delete(client, note):
    codes = [
        (await codex_file_attach_bytes(note.code, bytes([n]), filename=f"{n}.txt")).file_code
        for n in range(2)
    ]

    patched = await client.patch(f"{NOTES}/{note.code}/files/FILE@{codes[0]}", json={"title": "Первый"})
    ordered = await client.put(f"{NOTES}/{note.code}/files/order", json={"codes": [codes[1], codes[0]]})
    foreign = await client.put(f"{NOTES}/{note.code}/files/order", json={"codes": ["0000000000"]})
    detached = await client.delete(f"{NOTES}/{note.code}/files/{codes[1]}")
    missing = await client.patch(f"{NOTES}/{note.code}/files/{codes[1]}", json={"title": "x"})

    assert patched.status_code == 200 and patched.json()["title"] == "Первый"
    assert [row["code"] for row in ordered.json()] == [f"FILE@{codes[1]}", f"FILE@{codes[0]}"]
    assert foreign.status_code == 400 and foreign.json()["code"] == "codex.file.not_found"
    assert detached.status_code == 204
    assert missing.status_code == 404 and missing.json()["code"] == "codex.file.not_found"
    assert await _order(note.code) == [codes[0]]
    assert await file_owners(codes[1]) == []


@pytest.mark.parametrize("body", [{"title": "т" * (FILE_TITLE_MAX + 1)}, {"name": "x"}])
async def test_patch_over_the_limit_or_with_an_extra_field_is_422(client, note, body):
    bound = await codex_file_attach_bytes(note.code, PNG, filename="x.png", title="Было")

    response = await client.patch(f"{NOTES}/{note.code}/files/{bound.file_code}", json=body)

    assert response.status_code == 422
    assert (await file_crud.codex_file_get(note.code, bound.file_code)).title == "Было"


async def test_a_deleted_note_s_files_are_read_but_not_changed(client, note):
    bound = await codex_file_attach_bytes(note.code, PNG, filename="x.png")
    await note_crud.note_delete(note.code)

    listed = await client.get(f"{NOTES}/{note.code}/files")
    detached = await client.delete(f"{NOTES}/{note.code}/files/{bound.file_code}")

    assert listed.status_code == 200 and len(listed.json()) == 1
    assert detached.status_code == 409 and detached.json()["code"] == "codex.note.deleted"
    assert len(await file_owners(bound.file_code)) == 1


async def test_a_soft_deleted_codex_s_note_files_are_read_but_not_changed(client, codex, note):
    """The note itself is live, its codex is not: the soft deletion keeps the files for the
    restore, so no route changes them — and the storage owner stays."""
    bound = await codex_file_attach_bytes(note.code, PNG, filename="x.png", title="Было")
    await codex_crud.codex_delete(codex.code)

    listed = await client.get(f"{NOTES}/{note.code}/files")
    patched = await client.patch(f"{NOTES}/{note.code}/files/{bound.file_code}", json={"title": "x"})
    ordered = await client.put(f"{NOTES}/{note.code}/files/order", json={"codes": [bound.file_code]})
    detached = await client.delete(f"{NOTES}/{note.code}/files/{bound.file_code}")

    assert listed.status_code == 200 and len(listed.json()) == 1
    for response in (patched, ordered, detached):
        assert response.status_code == 409
        assert response.json()["code"] == "codex.codex.deleted"
    assert (await file_crud.codex_file_get(note.code, bound.file_code)).title == "Было"
    assert len(await file_owners(bound.file_code)) == 1


async def test_patch_of_a_file_the_file_manager_deleted_is_404_and_writes_nothing(client, note):
    bound = await codex_file_attach_bytes(note.code, PNG, filename="x.png", title="Было")
    await file_delete(bound.file_code)

    response = await client.patch(f"{NOTES}/{note.code}/files/{bound.file_code}", json={"title": "Стало"})

    assert response.status_code == 404
    assert response.json()["code"] == "codex.file.not_found"
    assert (await file_crud.codex_file_get(note.code, bound.file_code)).title == "Было"
