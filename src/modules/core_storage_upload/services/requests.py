"""Upload requests: an upload asked for now and sent later, by a client with no path on the server.

An agent whose MCP server runs elsewhere asks ``attach_file``; the holder and the agent's rights
are checked, and the request is written to ``core_storage_upload_request`` — the holder, the
workspace, what the agent asked the holder for (``payload``), the name hint, the expiry. The
client gets a short address with the request's random token (``/storage/upload?token=…``) and
sends the bytes there (``curl -T``); no data of the request rides in the address, and only the
token's sha256 is stored. The request outlives a restart of the backend and is taken by any of
its processes.

When the bytes come, the request is found by its token, the holder is asked again with the
request's workspace — a task may be deleted, a mount may have lost the agent's right in the
minutes between — and the request is claimed for this one upload; then the body is read, the
holder takes the file with the payload, and the request is deleted. A request is completed once:
a second PUT, a PUT while one is in flight, an expired or never opened token — one 404. An upload
that fails before the binding — over the ceiling, the client gone, the holder refusing — gives the
request back for another try until it expires.

The answer to the PUT is in the words of whoever opens the requests (``register_upload_answer``)
— the agent surface — since this module knows no agent.
"""

from __future__ import annotations

import hashlib
import secrets
from collections.abc import AsyncIterable, Mapping
from datetime import timedelta
from typing import Any
from urllib.parse import quote

import anyio

from src.core.backend_launch import base_url
from src.core.config import get_config
from src.core.loggers import get_logger
from src.core.router.storage import STORAGE_PREFIX
from src.core.utils.date import utc_now
from src.modules.core_storage.services.registration import file_spool
from src.modules.core_storage_upload.constants import (
    LOG_CHANNEL,
    ROUTER_PREFIX,
    TOKEN_BYTES,
    UPLOAD_ROUTE,
)
from src.modules.core_storage_upload.crud import request as request_crud
from src.modules.core_storage_upload.dto import (
    AttachedFile,
    Payload,
    UploadAddress,
    UploadAnswer,
    UploadRequest,
)
from src.modules.core_storage_upload.errors import (
    AlreadyHeld,
    RequestForeignHolder,
    RequestNotFound,
)
from src.modules.core_storage_upload.services.holders import upload_holder
from src.modules.core_storage_upload.services.intake import refuse_oversize, sent_name
from src.modules.core_storage_upload.settings import request_ttl

_LOG = get_logger(LOG_CHANNEL)

_answer: UploadAnswer | None = None


def register_upload_answer(answer: UploadAnswer) -> None:
    """How the PUT completing a request is answered — by the one who opens the requests. Without
    it the answer is the file's bare code, title and description."""
    global _answer
    _answer = answer


def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def upload_path(token: str) -> str:
    return f"{STORAGE_PREFIX}{ROUTER_PREFIX}{UPLOAD_ROUTE}?token={quote(token, safe='')}"


async def open_upload_request(
    holder_code: str,
    *,
    workspace: str,
    payload: Payload,
    filename_hint: str = "",
    ttl: timedelta | None = None,
) -> UploadAddress:
    """Ask for an upload into ``holder_code`` by the agent of ``workspace``; the address to send
    the bytes to.

    Everything that can be refused now is: the name hint (``FilenameRefused``; only its last path
    segment is kept), the holder and the agent's rights in ``workspace``, what the payload asks
    (``HolderRefused``). Nothing is bound. ``ttl`` — by default the module's setting at this
    moment.
    """
    lifetime = request_ttl() if ttl is None else ttl
    if lifetime <= timedelta(0):
        raise ValueError(f"An upload request needs a positive lifetime, got {lifetime}")
    hint = sent_name(filename_hint)
    holder, bare = upload_holder(holder_code)
    await holder.check(bare, payload, workspace=workspace)
    token = secrets.token_urlsafe(TOKEN_BYTES)
    row = await request_crud.request_create(
        token_hash=token_hash(token),
        holder=holder_code.strip(),
        workspace_code=workspace,
        filename=hint,
        payload=dict(payload),
        expires_at=utc_now() + lifetime,
    )
    path = upload_path(token)
    return UploadAddress(path=path, url=base_url(get_config()) + path, expires_at=row.expires_at)


async def upload_with_request(
    token: str,
    chunks: AsyncIterable[bytes],
    *,
    holder: str | None = None,
    filename: str | None = None,
    declared_size: int | None = None,
) -> Mapping[str, Any]:
    """Take the body sent for an open request, bind it as the request says, answer as the opener
    does.

    Refused before the body: no open request under the token (``RequestNotFound``), a ``holder``
    the PUT names other than the request's, a ``filename`` the storage could not keep (it replaces
    the hint), the holder asked again with the request's workspace (``HolderRefused``), the
    declared size. The bytes the holder has already answer with that file and complete the
    request.
    """
    hashed = token_hash(token.strip())
    row = await request_crud.request_open(hashed, utc_now())
    if row is None:
        raise RequestNotFound()
    request = UploadRequest(
        holder=row.holder,
        workspace=row.workspace_code,
        payload=row.payload or {},
        filename=row.filename,
        expires_at=row.expires_at,
    )
    if holder is not None and holder.strip().upper() != request.holder.upper():
        raise RequestForeignHolder(request.holder, holder)
    name = request.filename if filename is None else sent_name(filename)
    keeper, bare = upload_holder(request.holder)
    await keeper.check(bare, request.payload, workspace=request.workspace)
    refuse_oversize(declared_size)
    if not await request_crud.request_claim(hashed, utc_now()):
        raise RequestNotFound()
    try:
        async with file_spool(chunks) as spooled:
            attached = await keeper.attach(
                bare, spooled, request.payload, filename=name, workspace=request.workspace
            )
    except AlreadyHeld as held:
        attached = held.attached
    except BaseException:
        # A cancelled upload (the server stopping) would cancel this await too, and the request
        # would stay claimed until it expires.
        with anyio.CancelScope(shield=True):
            await request_crud.request_give_back(hashed)
        raise
    try:
        await request_crud.request_delete(hashed)
    except Exception:
        # The file is attached: the client is answered so. The claimed row opens nothing and
        # goes with the cleanup when it expires.
        _LOG.exception("core_storage_upload: a completed upload request was not deleted")
    return await _answered(request, attached)


async def purge_expired_requests() -> int:
    """Delete the requests whose time is over — the cleanup's job; the number deleted."""
    return await request_crud.request_purge_expired(utc_now())


async def _answered(request: UploadRequest, attached: AttachedFile) -> Mapping[str, Any]:
    if _answer is not None:
        return await _answer(request, attached)
    return {
        "code": attached.file_code,
        "title": attached.title,
        "description": attached.description,
    }


__all__ = [
    "open_upload_request",
    "purge_expired_requests",
    "register_upload_answer",
    "token_hash",
    "upload_path",
    "upload_with_request",
]
