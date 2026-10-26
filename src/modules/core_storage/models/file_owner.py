"""ORM ``core_storage_file_owner`` — who holds a file, and so whether the file is still needed.

An owner is an opaque triple the consumer chooses: ``owner_type`` + ``owner_id`` name its entity,
``owner_key`` the place inside it (``''`` — the entity as a whole). One entity holding a file in
two places is two rows: taking the file out of one place releases exactly that row, and the
module counts whether anything still holds the file.

``original_filename`` + ``original_extension`` is the name the owner brought the file under,
split before its last suffix with the case kept (``names.split_filename``). A name belongs to a
place, not to the bytes, so two owners of one content keep two names. The module only keeps
them — to show the file and to hand it out under its name; the type and the extension on disk
come from the bytes (``core_storage_file``).

``created_at`` is when the place took the file: a revived row takes it anew.

There is no FK to the owner — the module knows no consumer — so the consumer releases its rows
itself. A released owner is a row with ``deleted_at``; taking the file again revives the row.
``RESTRICT`` on the file keeps a file with any owner row from being deleted: the cleanup task
removes the released owners first.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import ForeignKey, Index, String, text
from sqlalchemy.orm import Mapped, mapped_column

from src.core.database import SoftDeleteMixin
from src.core.database.runtime import Base
from src.core.database.types import timestamp
from src.core.utils.date import utc_now
from src.modules.core_storage.constants import (
    CODE_LEN,
    EXTENSION_MAX,
    ORIGINAL_FILENAME_MAX,
    OWNER_ID_MAX,
    OWNER_KEY_MAX,
    OWNER_TYPE_MAX,
)
from src.modules.core_storage.models.file import CoreStorageFile


class CoreStorageFileOwner(SoftDeleteMixin, Base):
    __tablename__ = "core_storage_file_owner"
    # Every file of an owner, to release the owner at once when its entity is deleted.
    __table_args__ = (Index("ix_core_storage_file_owner_owner", "owner_type", "owner_id"),)

    file_code: Mapped[str] = mapped_column(
        String(CODE_LEN),
        ForeignKey(
            CoreStorageFile.code,
            name="fk_core_storage_file_owner_file_code",
            ondelete="RESTRICT",
        ),
        primary_key=True,
    )
    owner_type: Mapped[str] = mapped_column(String(OWNER_TYPE_MAX), primary_key=True)
    owner_id: Mapped[str] = mapped_column(String(OWNER_ID_MAX), primary_key=True)
    owner_key: Mapped[str] = mapped_column(
        String(OWNER_KEY_MAX), primary_key=True, default="", server_default=text("''")
    )
    original_filename: Mapped[str] = mapped_column(
        String(ORIGINAL_FILENAME_MAX), default="", server_default=text("''")
    )
    original_extension: Mapped[str] = mapped_column(
        String(EXTENSION_MAX), default="", server_default=text("''")
    )
    created_at: Mapped[datetime] = mapped_column(timestamp(), default=utc_now)


__all__ = ["CoreStorageFileOwner"]
