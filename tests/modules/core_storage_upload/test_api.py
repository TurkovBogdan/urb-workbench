"""The person's upload: ``POST /storage/upload?holder=`` from the app's own page, the file as the
body.

Who may write is decided before a byte of the body is read: the app's own page (``Origin``
present and allowed) or a token — never a request with neither, which is how ``curl`` or a script
on the machine would otherwise write into any task. Then the name, the holder and the declared
size; a body running past the ceiling stops there. Every refusal is checked by the state after it:
no stored file, no spare bytes in the storage's temporary folder.
"""

from __future__ import annotations

import pytest
from sqlalchemy import func, select

from src.core.database import session_scope
from src.modules.core_storage import settings as storage_settings
from src.modules.core_storage.constants import ORIGINAL_FILENAME_MAX
from src.modules.core_storage.models import CoreStorageFile
from src.modules.core_storage.services.ownership import file_owners
from src.modules.core_storage_upload.errors import HolderRefused, RefusalKind

from .conftest import OWN_ORIGIN, UPLOAD, StorageSettings, UnreadBody, leftovers

pytestmark = pytest.mark.db

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64
MB = 1024 * 1024


async def _stored_count() -> int:
    async with session_scope() as s:
        return (await s.execute(select(func.count()).select_from(CoreStorageFile))).scalar_one()


async def _upload(client, data, *, headers=OWN_ORIGIN, method="post", **query):
    return await getattr(client, method)(
        UPLOAD, params={"holder": "TEST@1", **query}, content=data, headers=headers
    )


async def test_the_body_becomes_the_holder_s_file_and_the_answer_is_the_holder_s(
    db, client, holder
):
    response = await _upload(client, PNG, filename="Снимок.PNG", title="Вход", description="d")

    assert response.status_code == 201, response.text
    code = response.json()["file"]
    assert response.json() == {"holder": "TEST@1", "file": code, "title": "Вход"}
    asked = {"title": "Вход", "description": "d"}
    assert holder.checks == [("1", asked, None)]
    assert holder.attached == [("1", "Снимок.PNG", asked, None)]
    owners = await file_owners(code)
    assert [(p.owner.id, p.original_filename, p.original_extension) for p in owners] == [
        ("1", "Снимок", ".PNG")
    ]
    assert leftovers(db.tmp) == []


async def test_a_put_from_the_page_is_taken_too(db, client, holder):
    response = await _upload(client, b"x", method="put", filename="x.txt")

    assert response.status_code == 201, response.text


async def test_a_name_that_came_with_a_path_keeps_its_last_segment(db, client, holder):
    await _upload(client, b"log\n", filename="C:\\логи\\сборка.log")

    assert holder.attached[0][1] == "сборка.log"


async def test_no_origin_and_no_token_is_401_before_the_body_and_stores_nothing(
    db, client, holder
):
    """What ``curl`` or a script on the machine sends: no browser page, no permission."""
    body = UnreadBody()

    response = await client.post(
        UPLOAD,
        params={"holder": "TEST@1", "filename": "x.png"},
        content=body,
        headers={"Content-Length": "16"},
    )

    assert body.pulled is False
    assert response.status_code == 401
    assert response.json()["code"] == "core_storage_upload.request.unauthorized"
    assert holder.checks == []
    assert await _stored_count() == 0
    assert leftovers(db.tmp) == []


async def test_a_page_of_another_site_is_403_before_the_body(db, client, holder):
    body = UnreadBody()

    response = await _upload(
        client,
        body,
        filename="x.png",
        headers={"Origin": "http://evil.example", "Content-Type": "text/plain", "Content-Length": "16"},
    )

    assert body.pulled is False
    assert response.status_code == 403
    assert response.json()["code"] == "origin_refused"
    assert holder.checks == []
    assert await _stored_count() == 0


@pytest.mark.parametrize("holder_code", ["NOPE@1", "TEST@", "TEST", ""])
async def test_a_code_no_holder_reads_is_400_before_the_body(db, client, holder, holder_code):
    body = UnreadBody()

    response = await client.post(
        UPLOAD,
        params={"holder": holder_code, "filename": "x.png"},
        content=body,
        headers={**OWN_ORIGIN, "Content-Length": "16"},
    )

    assert body.pulled is False
    assert response.status_code == 400
    assert response.json()["code"] == "core_storage_upload.holder.unknown"
    assert "TEST@" in response.json()["error"]
    assert await _stored_count() == 0


async def test_a_holder_code_is_read_in_any_case(db, client, holder):
    response = await client.post(
        UPLOAD, params={"holder": "test@1", "filename": "x.txt"}, content=b"x", headers=OWN_ORIGIN
    )

    assert response.status_code == 201, response.text
    assert holder.attached[0][0] == "1"


@pytest.mark.parametrize(
    ("name", "code"),
    [
        ("снимок\x00.png", "core_storage_upload.filename.control_character"),
        ("снимок\n.png", "core_storage_upload.filename.control_character"),
        ("dir\x07/снимок.png", "core_storage_upload.filename.control_character"),
        ("n" * (ORIGINAL_FILENAME_MAX + 1) + ".png", "core_storage_upload.filename.too_long"),
    ],
)
async def test_a_name_the_storage_cannot_keep_is_400_before_the_body(
    db, client, holder, name, code
):
    body = UnreadBody()

    response = await _upload(
        client, body, filename=name, headers={**OWN_ORIGIN, "Content-Length": "16"}
    )

    assert body.pulled is False
    assert response.status_code == 400
    assert response.json()["code"] == code
    assert holder.checks == []
    assert await _stored_count() == 0
    assert leftovers(db.tmp) == []


async def test_a_body_announced_over_the_ceiling_is_413_before_a_byte_is_read(db, client, holder):
    storage_settings.set_current(StorageSettings(max_file_size_mb=1))
    body = UnreadBody()

    response = await _upload(
        client, body, filename="big.bin", headers={**OWN_ORIGIN, "Content-Length": str(MB + 1)}
    )

    assert body.pulled is False
    assert response.status_code == 413
    assert response.json()["code"] == "core_storage_upload.file.too_large"
    assert response.json()["params"] == {"limit": MB, "limit_mb": 1}
    assert holder.attached == []
    assert await _stored_count() == 0
    assert leftovers(db.tmp) == []


async def test_a_stream_running_past_the_ceiling_is_413_and_nothing_is_stored(db, client, holder):
    storage_settings.set_current(StorageSettings(max_file_size_mb=1))

    async def chunks():
        for _ in range(3):
            yield b"x" * (MB // 2 + 1)

    response = await _upload(client, chunks(), filename="big.bin")

    assert response.status_code == 413
    assert response.json()["code"] == "core_storage_upload.file.too_large"
    assert holder.attached == []
    assert await _stored_count() == 0
    assert leftovers(db.tmp) == []


@pytest.mark.parametrize(
    ("kind", "status"),
    [
        (RefusalKind.MISSING, 404),
        (RefusalKind.CONFLICT, 409),
        (RefusalKind.FORBIDDEN, 403),
        (RefusalKind.INVALID, 400),
    ],
)
async def test_a_holder_s_refusal_keeps_its_code_and_params_and_takes_its_status(
    db, client, holder, kind, status
):
    holder.refuse_check = HolderRefused(
        "no", kind=kind, code="test.holder.no", params={"field": "title"}
    )
    body = UnreadBody()

    response = await _upload(
        client, body, filename="x.png", headers={**OWN_ORIGIN, "Content-Length": "16"}
    )

    assert body.pulled is False
    assert response.status_code == status
    assert response.json()["code"] == "test.holder.no"
    assert response.json()["params"] == {"field": "title"}
    assert await _stored_count() == 0


async def test_the_same_bytes_again_are_409_with_the_file_they_are(db, client, holder):
    first = await _upload(client, PNG, filename="a.png")

    again = await _upload(client, PNG, filename="b.png")

    assert again.status_code == 409
    assert again.json()["code"] == "test.file.already_attached"
    assert again.json()["params"] == {"file": f"FILE@{first.json()['file']}"}
    assert await _stored_count() == 1
    assert leftovers(db.tmp) == []


async def test_a_refusal_at_the_binding_leaves_no_spare_bytes(db, client, holder):
    holder.refuse_attach = HolderRefused("deleted meanwhile", kind=RefusalKind.CONFLICT)

    response = await _upload(client, PNG, filename="x.png")

    assert response.status_code == 409
    assert leftovers(db.tmp) == []
