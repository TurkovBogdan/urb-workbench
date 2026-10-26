"""Upload requests: an upload asked for now and sent later, kept in the base and completed once.

A request is opened only for an upload the holder would take, and nothing is bound until the
bytes come. The address carries a random token and nothing else; only its sha256 is stored. When
the bytes come, the holder is asked again with the request's workspace and the payload lands in
the binding; a request is completed once — a second PUT, two PUTs at once, an expired or unknown
token get one 404 — and an upload that fails before the binding leaves it open for another try.
Every refusal is checked by the state after it.
"""

from __future__ import annotations

import asyncio
import hashlib
from datetime import timedelta
from urllib.parse import parse_qs, quote, urlsplit

import anyio
import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import func, select

from src.core.database import session_scope
from src.core.utils.date import utc_now
from src.modules.core_storage import settings as storage_settings
from src.modules.core_storage.constants import ORIGINAL_FILENAME_MAX
from src.modules.core_storage.models import CoreStorageFile
from src.modules.core_storage.services.ownership import file_owners
from src.modules.core_storage_upload import settings as upload_settings
from src.modules.core_storage_upload.errors import (
    FilenameRefused,
    HolderRefused,
    RefusalKind,
    RequestNotFound,
    UnknownHolder,
)
from src.modules.core_storage_upload.models import CoreStorageUploadRequest
from src.modules.core_storage_upload.services import requests as requests_module
from src.modules.core_storage_upload.services.requests import (
    open_upload_request,
    purge_expired_requests,
    register_upload_answer,
    upload_with_request,
)

from .conftest import StorageSettings, UnreadBody, UploadSettings, leftovers, upload_app

pytestmark = pytest.mark.db

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64
TOO_LONG = "n" * (ORIGINAL_FILENAME_MAX + 1) + ".txt"
ASKED = {"title": "Экран", "description": "вход"}


async def _stored_count() -> int:
    async with session_scope() as s:
        return (await s.execute(select(func.count()).select_from(CoreStorageFile))).scalar_one()


async def _requests() -> list[CoreStorageUploadRequest]:
    async with session_scope() as s:
        return list((await s.execute(select(CoreStorageUploadRequest))).scalars().all())


async def _open(**kwargs):
    kwargs.setdefault("workspace", "WS1")
    kwargs.setdefault("payload", ASKED)
    return await open_upload_request("TEST@1", **kwargs)


def _token(address) -> str:
    return parse_qs(urlsplit(address.path).query)["token"][0]


# ── opening ───────────────────────────────────────────────────────────────────


async def test_a_request_is_kept_under_its_token_s_hash_and_the_address_carries_nothing_else(
    db, holder, monkeypatch
):
    monkeypatch.setenv("SERVER_HOST", "0.0.0.0")
    monkeypatch.setenv("SERVER_PORT", "22140")
    before = utc_now()

    address = await _open(filename_hint="../shots\\вход.png")

    token = _token(address)
    assert address.path == f"/storage/upload?token={token}"
    assert address.url == f"http://127.0.0.1:22140{address.path}"
    assert len(token) >= 43
    [row] = await _requests()
    assert row.token_hash == hashlib.sha256(token.encode()).hexdigest()
    assert (row.holder, row.workspace_code, row.payload, row.filename, row.claimed_at) == (
        "TEST@1", "WS1", ASKED, "вход.png", None
    )
    assert before + timedelta(minutes=15) - timedelta(seconds=1) <= row.expires_at
    assert row.expires_at == address.expires_at
    assert holder.checks == [("1", ASKED, "WS1")]
    assert holder.attached == []


async def test_two_requests_for_one_upload_have_two_tokens(db):
    first, second = await _open(), await _open()

    assert _token(first) != _token(second)
    assert len(await _requests()) == 2


async def test_a_holder_refusal_opens_no_request(db, holder):
    holder.refuse_check = HolderRefused("no", kind=RefusalKind.FORBIDDEN, code="test.no")

    with pytest.raises(HolderRefused):
        await _open()

    assert await _requests() == []


@pytest.mark.parametrize("hint", [TOO_LONG, "shot\x01\nname.png"])
async def test_a_name_hint_the_storage_cannot_keep_opens_no_request(db, holder, hint):
    with pytest.raises(FilenameRefused):
        await _open(filename_hint=hint)

    assert holder.checks == []
    assert await _requests() == []


async def test_an_unknown_holder_opens_no_request(db):
    with pytest.raises(UnknownHolder):
        await open_upload_request("NOPE@1", workspace="WS1", payload={})

    assert await _requests() == []


async def test_a_request_needs_a_positive_lifetime(db):
    with pytest.raises(ValueError):
        await _open(ttl=timedelta(0))


async def test_the_lifetime_is_the_setting_at_the_moment_of_opening(db):
    upload_settings.set_current(UploadSettings(request_ttl_minutes=2))

    address = await _open()

    assert address.expires_at - utc_now() <= timedelta(minutes=2)
    assert address.expires_at - utc_now() > timedelta(minutes=1)


# ── completing ────────────────────────────────────────────────────────────────


async def test_the_bytes_go_where_the_request_says_and_the_answer_is_the_opener_s(
    db, client, holder
):
    address = await _open(filename_hint="вход.png")
    answered: list[tuple] = []

    async def answer(request, attached):
        answered.append((request.workspace, request.payload, attached.title))
        return {"code": f"FILE@{attached.file_code}", "workspace": request.workspace}

    register_upload_answer(answer)

    response = await client.put(address.path, content=PNG)

    assert response.status_code == 200, response.text
    code = response.json()["code"].removeprefix("FILE@")
    assert response.json() == {"code": f"FILE@{code}", "workspace": "WS1"}
    assert answered == [("WS1", ASKED, "Экран")]
    assert holder.attached == [("1", "вход.png", ASKED, "WS1")]
    assert [(p.owner.id, p.original_filename) for p in await file_owners(code)] == [("1", "вход")]
    assert await _requests() == []
    assert leftovers(db.tmp) == []


async def test_without_an_answer_registered_the_file_s_code_comes_back(db, client):
    address = await _open()

    response = await client.put(address.path, content=b"x")

    assert response.status_code == 200
    assert response.json()["title"] == "Экран"
    assert set(response.json()) == {"code", "title", "description"}


async def test_a_request_is_completed_once(db, client, holder):
    address = await _open()

    first = await client.put(address.path, content=PNG)
    again = await client.put(address.path, content=b"other")

    assert first.status_code == 200
    assert (again.status_code, again.json()["code"]) == (404, "core_storage_upload.request.not_found")
    assert len(holder.attached) == 1
    assert await _stored_count() == 1


@pytest.mark.parametrize("token", ["", "garbage", "x" * 43, "Ð"])
async def test_an_unknown_token_is_404_before_the_body(db, client, token):
    await _open()
    body = UnreadBody()

    response = await client.put(
        f"/storage/upload?token={quote(token)}", content=body, headers={"Content-Length": "4"}
    )

    assert body.pulled is False
    assert (response.status_code, response.json()["code"]) == (404, "core_storage_upload.request.not_found")
    assert await _stored_count() == 0


async def test_an_expired_request_is_404_and_stores_nothing(db, client, holder, monkeypatch):
    address = await _open()
    later = utc_now() + timedelta(minutes=15)
    monkeypatch.setattr(requests_module, "utc_now", lambda: later)

    response = await client.put(address.path, content=PNG)

    assert (response.status_code, response.json()["code"]) == (404, "core_storage_upload.request.not_found")
    assert holder.attached == []
    assert await _stored_count() == 0


async def test_a_request_is_taken_until_its_last_second(db, client, monkeypatch):
    address = await _open()
    just_before = address.expires_at - timedelta(seconds=1)
    monkeypatch.setattr(requests_module, "utc_now", lambda: just_before)

    assert (await client.put(address.path, content=b"in time")).status_code == 200


async def test_two_puts_at_once_bind_once(db, holder):
    """The second PUT comes while the first one's body is still arriving: the request is claimed,
    and the second finds no open request — whichever way the race runs, one file is bound."""
    address = await _open()
    token = _token(address)
    arrived, release = asyncio.Event(), asyncio.Event()

    async def slow():
        yield b"part"
        arrived.set()
        await release.wait()
        yield b"rest"

    first = asyncio.create_task(upload_with_request(token, slow()))
    await arrived.wait()
    with pytest.raises(RequestNotFound):
        await upload_with_request(token, _chunks(b"second"))
    release.set()
    await first

    assert [entry[0] for entry in holder.attached] == ["1"]
    assert await _requests() == []
    assert leftovers(db.tmp) == []


async def test_two_puts_started_together_bind_once(db, holder):
    address = await _open()
    token = _token(address)

    results = await asyncio.gather(
        *(upload_with_request(token, _chunks(f"body {n}".encode())) for n in range(5)),
        return_exceptions=True,
    )

    assert sum(1 for result in results if not isinstance(result, BaseException)) == 1
    assert all(isinstance(r, RequestNotFound) for r in results if isinstance(r, BaseException))
    assert len(holder.attached) == 1
    assert await _stored_count() == 1


async def test_the_holder_is_asked_again_with_the_request_s_workspace_before_the_body(
    db, client, holder
):
    address = await _open()
    holder.refuse_check = HolderRefused(
        "not editable for you", kind=RefusalKind.FORBIDDEN, code="test.forbidden"
    )
    body = UnreadBody()

    response = await client.put(address.path, content=body, headers={"Content-Length": "16"})

    assert body.pulled is False
    assert (response.status_code, response.json()["code"]) == (403, "test.forbidden")
    assert holder.checks[-1] == ("1", ASKED, "WS1")
    assert await _stored_count() == 0
    [row] = await _requests()
    assert row.claimed_at is None


@pytest.mark.parametrize(
    ("kind", "status"),
    [
        (RefusalKind.MISSING, 404),
        (RefusalKind.CONFLICT, 409),
        (RefusalKind.FORBIDDEN, 403),
        (RefusalKind.INVALID, 400),
    ],
)
async def test_a_holder_gone_between_the_request_and_the_bytes_binds_nothing(
    db, client, holder, kind, status
):
    address = await _open()
    holder.refuse_check = HolderRefused("gone", kind=kind, code="test.gone")

    response = await client.put(address.path, content=PNG)

    assert (response.status_code, response.json()["code"]) == (status, "test.gone")
    assert holder.attached == []
    assert await _stored_count() == 0


async def test_a_refusal_at_the_binding_gives_the_request_back(db, client, holder):
    address = await _open()
    holder.refuse_attach = HolderRefused("deleted meanwhile", kind=RefusalKind.CONFLICT)

    refused = await client.put(address.path, content=PNG)
    holder.refuse_attach = None
    retried = await client.put(address.path, content=PNG)

    assert refused.status_code == 409
    assert retried.status_code == 200
    assert await _requests() == []
    assert leftovers(db.tmp) == []


async def test_a_completed_request_left_undeleted_still_answers_with_the_file(
    db, client, holder, monkeypatch
):
    """The file is attached once the holder took it: a request row the database would not delete
    then is no failure of the upload — the claimed row opens nothing and expires."""
    address = await _open()

    async def locked(token_hash: str) -> None:
        raise RuntimeError("database is locked")

    monkeypatch.setattr(requests_module.request_crud, "request_delete", locked)

    response = await client.put(address.path, content=PNG)
    again = await client.put(address.path, content=PNG)

    assert response.status_code == 200
    assert holder.attached
    assert again.status_code == 404
    assert await _stored_count() == 1


async def test_an_upload_cancelled_mid_body_gives_the_request_back(db, holder):
    """A cancel scope cancels every await inside it, the give-back's too, unless shielded — a
    server stopping mid-upload must not leave the request claimed until it expires."""
    address = await _open()

    async def stalled():
        yield PNG[:8]
        await anyio.sleep(3600)

    with anyio.move_on_after(0.2):
        await upload_with_request(_token(address), stalled())

    [row] = await _requests()
    assert row.claimed_at is None
    assert holder.attached == []
    assert leftovers(db.tmp) == []


@pytest.mark.pure
@pytest.mark.parametrize("sent", [".", "..", " .. ", "dir/..", "...", "dir\\."])
def test_a_name_of_dots_only_names_nothing(sent):
    from src.modules.core_storage_upload.services.intake import sent_name

    assert sent_name(sent) == ""
    assert sent_name(".env") == ".env"
    assert sent_name("a..b.png") == "a..b.png"


async def test_bytes_the_holder_has_already_complete_the_request_with_that_file(db, client, holder):
    first = await client.put((await _open()).path, content=PNG)
    second_address = await _open()

    second = await client.put(second_address.path, content=PNG)

    assert second.status_code == 200
    assert second.json()["code"] == first.json()["code"]
    assert await _requests() == []
    assert await _stored_count() == 1


async def test_a_put_naming_another_holder_is_400_and_the_request_stays_open(db, client, holder):
    address = await _open()

    response = await client.put(f"{address.path}&holder=TEST@2", content=PNG)

    assert (response.status_code, response.json()["code"]) == (400, "core_storage_upload.request.foreign_holder")
    assert holder.attached == []
    assert len(await _requests()) == 1
    assert (await client.put(f"{address.path}&holder=test@1", content=b"x")).status_code == 200


async def test_a_request_outlives_a_restart_of_the_backend(db, holder):
    """Nothing is held in memory: a new app — a restarted backend, another process — takes the
    request the old one opened."""
    address = await _open()

    async with AsyncClient(transport=ASGITransport(app=upload_app()), base_url="http://test") as fresh:
        response = await fresh.put(address.path, content=PNG)

    assert response.status_code == 200, response.text
    assert len(holder.attached) == 1


async def test_the_put_names_the_file_and_keeps_only_its_last_segment(db, client, holder):
    address = await _open(filename_hint="hint.txt")

    await client.put(f"{address.path}&filename={quote('../dir' + chr(92) + 'отчёт.txt')}", content=b"x")

    assert holder.attached[0][1] == "отчёт.txt"


@pytest.mark.parametrize("name", [TOO_LONG, "x\x00.png", "a\nb.png", "bell\x07.txt"])
async def test_a_name_the_storage_cannot_keep_is_400_before_the_body_and_the_request_stays(
    db, client, holder, name
):
    address = await _open(filename_hint="hint.txt")
    body = UnreadBody()

    refused = await client.put(
        f"{address.path}&filename={quote(name, safe='')}", content=body, headers={"Content-Length": "4"}
    )

    assert body.pulled is False
    assert refused.status_code == 400
    assert refused.json()["code"].startswith("core_storage_upload.filename.")
    assert holder.attached == []
    accepted = await client.put(f"{address.path}&filename=short.txt", content=b"x")
    assert accepted.status_code == 200


async def test_over_the_ceiling_is_413_both_ways_keeps_nothing_and_the_request_stays(
    db, client, holder
):
    storage_settings.set_current(StorageSettings(max_file_size_mb=1))
    address = await _open()
    body = UnreadBody()

    announced = await client.put(
        address.path, content=body, headers={"Content-Length": str(1024 * 1024 + 1)}
    )

    async def streamed():
        for _ in range(3):
            yield b"0" * (512 * 1024 + 1)

    running = await client.put(address.path, content=streamed())

    assert body.pulled is False
    assert announced.status_code == running.status_code == 413
    assert announced.json()["params"] == {"limit": 1024 * 1024, "limit_mb": 1}
    assert announced.json()["error"] == "The file is over the 1048576-byte ceiling"
    assert holder.attached == []
    assert await _stored_count() == 0
    assert leftovers(db.tmp) == []
    retry = await client.put(address.path, content=b"small")
    assert retry.status_code == 200


async def test_a_body_that_breaks_off_keeps_nothing_and_the_request_stays(db, holder):
    address = await _open()
    token = _token(address)

    async def broken():
        yield b"part"
        raise ConnectionError("client gone")

    with pytest.raises(ConnectionError):
        await upload_with_request(token, broken())

    assert holder.attached == []
    assert leftovers(db.tmp) == []
    await upload_with_request(token, _chunks(b"whole"))
    assert len(holder.attached) == 1


# ── the cleanup ───────────────────────────────────────────────────────────────


async def test_the_cleanup_removes_the_expired_requests_only(db, monkeypatch):
    await _open(ttl=timedelta(minutes=1))
    kept = await _open(ttl=timedelta(minutes=30))
    later = utc_now() + timedelta(minutes=2)
    monkeypatch.setattr(requests_module, "utc_now", lambda: later)

    removed = await purge_expired_requests()

    assert removed == 1
    assert [row.expires_at for row in await _requests()] == [kept.expires_at]


async def _chunks(data: bytes):
    yield data
