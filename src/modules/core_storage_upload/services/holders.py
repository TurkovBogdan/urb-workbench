"""What takes an upload: a holder's code, read by the module that owns it.

The codes are the consumers', and this module sits under them and knows none. So each consumer
registers how its codes take a file (``register_upload_holder``): ``TASK`` — the task;
``NOTE`` / ``STAGE`` — the task they are in, the file marked as attached there; ``CODEX`` — a
codex note. A holder answers three things (``UploadHolder``): whether it would take a file at
all, asked before the body arrives; taking a spooled file under its own lock; and the file as its
list shows it, for the person's page.
"""

from __future__ import annotations

from src.modules.core_storage_upload.dto import UploadHolder
from src.modules.core_storage_upload.errors import UnknownHolder

_holders: dict[str, UploadHolder] = {}


def register_upload_holder(prefix: str, holder: UploadHolder) -> None:
    """Take uploads for ``<PREFIX>@<code>`` through ``holder``; the prefix is matched in any case.
    A second registration of one prefix replaces the first — ``configure`` runs again in a test
    harness."""
    word = prefix.strip().upper()
    if not word or "@" in word:
        raise ValueError(f"A holder prefix is one word before '@', got {prefix!r}")
    _holders[word] = holder


def upload_holder(code: str) -> tuple[UploadHolder, str]:
    """The holder ``code`` names and its bare code, upper case; ``UnknownHolder`` — none does."""
    prefix, at, bare = code.strip().partition("@")
    holder = _holders.get(prefix.upper()) if at else None
    if holder is None or not bare.strip():
        raise UnknownHolder(code, list(_holders))
    return holder, bare.strip().upper()


__all__ = ["register_upload_holder", "upload_holder"]
