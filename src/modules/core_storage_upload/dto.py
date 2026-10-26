"""What the module hands out and what a holder hands in: plain frozen values."""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Protocol

from src.modules.core_storage.dto import SpooledFile

# What the client asked the holder for — a title and a description, for the holders there are
# today. The upload module carries it from the request to the holder and never reads it: what it
# means is the holder's.
Payload = Mapping[str, Any]


@dataclass(frozen=True)
class AttachedFile:
    """A file a holder took: its code in the storage and what the holder calls it."""

    file_code: str
    title: str
    description: str


class HolderCheck(Protocol):
    """Every refusal the holder can give before the body arrives; returns nothing when none.

    ``workspace`` — the workspace whose agent sends the file (an upload request remembers it, a
    path on the server names it): the holder asks the agent's rights there as well — a task of
    that workspace, a codex note its mount lets the agent write. ``None`` — the person's own page.
    """

    def __call__(
        self, bare: str, payload: Payload, *, workspace: str | None = None
    ) -> Awaitable[None]: ...


class HolderAttach(Protocol):
    """Take a spooled file under the holder's own lock: its checks again, the storage, its row.
    ``AlreadyHeld`` — the holder has these bytes already, and nothing changed."""

    def __call__(
        self,
        bare: str,
        spooled: SpooledFile,
        payload: Payload,
        *,
        filename: str,
        workspace: str | None = None,
    ) -> Awaitable[AttachedFile]: ...


# ``(bare, attached) -> JSON-serialisable mapping`` — the file as the holder's own list shows it,
# the answer the person's page gets.
HolderAnswer = Callable[[str, AttachedFile], Awaitable[Mapping[str, Any]]]


@dataclass(frozen=True)
class UploadHolder:
    """How one kind of code takes an upload — registered by the module that owns the code.

    Each refusal is a ``HolderRefused`` with the holder's code and text: the module that knows
    the rule says what it means.
    """

    check: HolderCheck
    attach: HolderAttach
    answer: HolderAnswer


@dataclass(frozen=True)
class UploadRequest:
    """An upload request as it is kept: the holder the bytes go to, the workspace whose agent sends
    them, what it asked the holder for, the name to take when the PUT names none, and the moment
    it stops being open."""

    holder: str
    workspace: str
    payload: Payload
    filename: str
    expires_at: datetime


@dataclass(frozen=True)
class UploadAddress:
    """Where a client sends the bytes of an open request.

    ``path`` is right on any address the server is reached at; ``url`` is ``path`` on the
    server's own host and port, the way the app's other links are built. A caller that knows the
    address its client reached the server at prefixes ``path`` itself.
    """

    path: str
    url: str
    expires_at: datetime


# ``(request, attached) -> JSON-serialisable mapping`` — the answer to the PUT that completes a
# request, in the words of whoever opens the requests (``register_upload_answer``).
UploadAnswer = Callable[[UploadRequest, AttachedFile], Awaitable[Mapping[str, Any]]]


__all__ = [
    "AttachedFile",
    "HolderAnswer",
    "HolderAttach",
    "HolderCheck",
    "Payload",
    "UploadAddress",
    "UploadAnswer",
    "UploadHolder",
    "UploadRequest",
]
