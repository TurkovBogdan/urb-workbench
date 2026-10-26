"""ORM ``core_storage_upload_request`` — an upload a client asked for and has not sent yet.

The agent whose files are not on the server's disk asks ``attach_file``; the holder and its rights
are checked then, and the request is written here: the holder the bytes go to, the workspace whose
agent asked, what it asked the holder for (``payload`` — the module carries it and never reads
it), the name hint, and when the request stops being open. The client gets an address with the
request's token; only the token's sha256 is kept, so the table read by someone else opens nothing.

A request is no binding: the holder shows nothing until the bytes come. ``claimed_at`` is set
while an upload of it is in flight — a second PUT meanwhile finds no open request — and cleared
when that upload fails before the binding; a completed request is deleted. The hourly cleanup
deletes the expired ones.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import Index, String
from sqlalchemy.orm import Mapped, mapped_column

from src.core.database.runtime import Base
from src.core.database.types import json_value, timestamp
from src.core.utils.date import utc_now
from src.modules.core_storage_upload.constants import (
    FILENAME_MAX,
    HOLDER_MAX,
    TOKEN_HASH_LEN,
    WORKSPACE_MAX,
)


class CoreStorageUploadRequest(Base):
    __tablename__ = "core_storage_upload_request"
    __table_args__ = (
        # The cleanup looks requests up by when they stop being open.
        Index("ix_core_storage_upload_request_expires_at", "expires_at"),
    )

    token_hash: Mapped[str] = mapped_column(String(TOKEN_HASH_LEN), primary_key=True)
    holder: Mapped[str] = mapped_column(String(HOLDER_MAX))
    workspace_code: Mapped[str] = mapped_column(String(WORKSPACE_MAX))
    filename: Mapped[str] = mapped_column(String(FILENAME_MAX), default="", server_default="")
    payload: Mapped[dict[str, Any]] = mapped_column(json_value(), default=dict)
    claimed_at: Mapped[datetime | None] = mapped_column(timestamp(), nullable=True)
    expires_at: Mapped[datetime] = mapped_column(timestamp())
    created_at: Mapped[datetime] = mapped_column(timestamp(), default=utc_now)


__all__ = ["CoreStorageUploadRequest"]
