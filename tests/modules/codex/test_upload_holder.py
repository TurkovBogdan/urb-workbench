"""The person's upload into a codex note: ``POST /storage/upload?holder=CODEX@…`` with the file as
the body.

The route is ``core_storage_upload``'s; the holder ``CODEX@`` is this module's
(``file_holders.py``), registered as ``CodexModule.configure`` does. Only a live note of a live
codex takes a file; a codex code is refused by name. Every refusal is checked by the state after
it — no stored file, no binding, no spare bytes in the storage's temporary folder.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy import func, select

from src.core.api import register_exception_handlers
from src.core.database import session_scope
from src.core.router.storage import STORAGE_PREFIX
from src.modules.codex.api import router as codex_router
from src.modules.codex.crud import codex as codex_crud
from src.modules.codex.crud import file as file_crud
from src.modules.codex.crud import note as note_crud
from src.modules.codex.file_holders import register_file_holders
from src.modules.core_storage import settings as storage_settings
from src.modules.core_storage.models import CoreStorageFile
from src.modules.core_storage_upload.api import router as upload_router
from src.modules.core_storage_upload.constants import ROUTER_PREFIX as UPLOAD_PREFIX
from src.modules.core_storage_upload.services import holders as upload_holders

pytestmark = pytest.mark.db

NOTES = "/internal/codex/notes"
UPLOAD = f"{STORAGE_PREFIX}{UPLOAD_PREFIX}/upload"
# The app's own page, as the test client's host names it: the upload takes a browser's request
# only from there.
OWN_PAGE = {"Origin": "http://test"}
PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64
MB = 1024 * 1024


@pytest.fixture
async def client(db, monkeypatch: pytest.MonkeyPatch):
    """The module's routes and the upload's, and the holder the module registers, in fresh
    registries — as the assembled app has them."""
    monkeypatch.setattr(upload_holders, "_holders", {})
    register_file_holders()
    app = FastAPI()
    register_exception_handlers(app)
    app.include_router(codex_router, prefix="/internal/codex")
    app.include_router(upload_router, prefix=f"{STORAGE_PREFIX}{UPLOAD_PREFIX}")
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


@pytest.fixture
async def codex(client, storage):
    return await codex_crud.codex_create(segment="python", title="Python")


@pytest.fixture
async def note(codex):
    return await note_crud.note_create(parent_code=codex.code, segment="test", title="Тесты")


async def _stored_count() -> int:
    async with session_scope() as s:
        return (await s.execute(select(func.count()).select_from(CoreStorageFile))).scalar_one()


def _spare_files(storage) -> list[str]:
    return [path.name for path in storage.tmp.rglob("*") if path.is_file()]


class _UnreadBody:
    """A request body that must not be read: a refusal due before the body pulls nothing."""

    def __init__(self) -> None:
        self.pulled = False

    def __aiter__(self):
        return self

    async def __anext__(self) -> bytes:
        self.pulled = True
        raise AssertionError("the body was read before the refusal")


async def _upload(client, note_code: str, data, *, headers=None, **query):
    return await client.post(
        UPLOAD,
        params={"holder": f"CODEX@{note_code}", **query},
        content=data,
        headers={**OWN_PAGE, **(headers or {})},
    )


async def test_the_body_becomes_a_file_of_the_note_under_its_own_name(client, note, storage):
    response = await _upload(client, note.code, PNG, filename="Схема потока.png", title="Поток")

    assert response.status_code == 201, response.text
    row = response.json()
    assert {key: row[key] for key in (
        "note_code", "title", "original_filename", "original_extension", "type", "size",
    )} == {
        "note_code": f"CODEX@{note.code}",
        "title": "Поток",
        "original_filename": "Схема потока",
        "original_extension": ".png",
        "type": "image",
        "size": len(PNG),
    }
    assert [f"FILE@{one.file_code}" for one in await file_crud.codex_file_list(note.code)] == [row["code"]]
    assert _spare_files(storage) == []


async def test_the_same_bytes_again_are_refused_with_the_file_they_are(client, note):
    first = await _upload(client, note.code, PNG, filename="схема.png")

    again = await _upload(client, note.code, PNG, filename="копия.png")

    assert again.status_code == 409
    body = again.json()
    assert body["code"] == "codex.file.already_attached"
    assert body["params"] == {"file": first.json()["code"], "name": "схема.png", "type": "image"}
    assert len(await file_crud.codex_file_list(note.code)) == 1
    assert await _stored_count() == 1


async def test_a_codex_takes_no_file(client, codex):
    response = await _upload(client, codex.code, PNG, filename="x.png")

    assert response.status_code == 400
    assert response.json()["code"] == "codex.file.holder_is_codex"
    assert await _stored_count() == 0


async def test_a_deleted_note_takes_no_file(client, note):
    await note_crud.note_delete(note.code)

    response = await _upload(client, note.code, PNG, filename="x.png")

    assert response.status_code == 409
    assert response.json()["code"] == "codex.note.deleted"
    assert await file_crud.codex_file_list(note.code) == []
    assert await _stored_count() == 0


async def test_a_note_of_a_deleted_codex_takes_no_file(client, codex, note):
    await codex_crud.codex_delete(codex.code)

    response = await _upload(client, note.code, PNG, filename="x.png")

    assert response.status_code == 409
    assert response.json()["code"] == "codex.codex.deleted"
    assert await _stored_count() == 0


async def test_an_unknown_note_is_404(client, codex):
    response = await _upload(client, "0000000000", PNG, filename="x.png")

    assert response.status_code == 404
    assert response.json()["code"] == "codex.note.not_found"
    assert await _stored_count() == 0


async def test_the_person_needs_no_mount_to_upload(client, note, workspace):
    """The agent writes only where a mount lets it; the person's page needs none."""
    response = await _upload(client, note.code, b"x", filename="x.txt")

    assert response.status_code == 201, response.text


async def test_a_body_announced_over_the_ceiling_is_413_before_a_byte_is_read(
    client, note, storage, monkeypatch
):
    monkeypatch.setattr(storage_settings, "_current", SimpleNamespace(max_file_size_mb=1))
    body = _UnreadBody()

    response = await _upload(
        client, note.code, body, filename="big.bin", headers={"Content-Length": str(MB + 1)}
    )

    assert body.pulled is False
    assert response.status_code == 413
    assert response.json()["code"] == "core_storage_upload.file.too_large"
    assert response.json()["params"] == {"limit": MB, "limit_mb": 1}
    assert await file_crud.codex_file_list(note.code) == []
    assert await _stored_count() == 0
    assert _spare_files(storage) == []


async def test_a_stream_running_past_the_ceiling_is_413_and_nothing_is_stored(
    client, note, storage, monkeypatch
):
    monkeypatch.setattr(storage_settings, "_current", SimpleNamespace(max_file_size_mb=1))

    async def chunks():
        for _ in range(3):
            yield b"x" * (MB // 2 + 1)

    response = await _upload(client, note.code, chunks(), filename="big.bin")

    assert response.status_code == 413
    assert response.json()["code"] == "core_storage_upload.file.too_large"
    assert await file_crud.codex_file_list(note.code) == []
    assert await _stored_count() == 0
    assert _spare_files(storage) == []


@pytest.mark.parametrize(
    ("field", "value", "code", "params"),
    [
        ("filename", "схема\x00.png", "core_storage_upload.filename.control_character", None),
        ("filename", "схема\r.png", "core_storage_upload.filename.control_character", None),
        ("title", "Поток\x00", "codex.file.control_character", {"field": "title"}),
        ("description", "как\x00идёт", "codex.file.control_character", {"field": "description"}),
    ],
)
async def test_a_control_character_is_400_before_the_body(
    client, note, storage, field, value, code, params
):
    body = _UnreadBody()

    response = await _upload(
        client,
        note.code,
        body,
        headers={"Content-Length": "16"},
        **{"filename": "x.png", field: value},
    )

    assert body.pulled is False
    assert response.status_code == 400
    assert response.json()["code"] == code
    assert response.json()["params"] == params
    assert await file_crud.codex_file_list(note.code) == []
    assert await _stored_count() == 0
    assert _spare_files(storage) == []


async def test_a_retitle_with_a_nul_is_400_and_changes_nothing(client, note):
    first = await _upload(client, note.code, PNG, filename="схема.png", title="Было")
    file_code = first.json()["code"]

    response = await client.patch(f"{NOTES}/{note.code}/files/{file_code}", json={"description": "x\x00"})

    assert response.status_code == 400
    assert response.json()["code"] == "codex.file.control_character"
    rows = await file_crud.codex_file_list(note.code)
    assert [(row.title, row.description) for row in rows] == [("Было", "")]


async def test_a_page_of_another_site_is_refused_before_the_body(client, note):
    response = await _upload(
        client, note.code, PNG, filename="x.png", headers={"Origin": "http://evil.example"}
    )

    assert response.status_code == 403
    assert response.json()["code"] == "origin_refused"
    assert await _stored_count() == 0


async def test_a_request_with_no_page_and_no_token_is_401_and_stores_nothing(client, note):
    response = await client.post(
        UPLOAD, params={"holder": f"CODEX@{note.code}", "filename": "x.png"}, content=PNG
    )

    assert response.status_code == 401
    assert response.json()["code"] == "core_storage_upload.request.unauthorized"
    assert await file_crud.codex_file_list(note.code) == []
    assert await _stored_count() == 0
