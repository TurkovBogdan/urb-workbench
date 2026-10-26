"""ORM ``core_storage_file`` — a stored file: the bytes in one of the stores and what they are.

The row does not keep a path: the path follows from the store, the code and the extension
(``layout.StorageLayout.file_path``). Nothing of the file's use lives here — no name, no owner:
the row describes the bytes, and one content can stand behind several places under several
names. Who holds the file, and under which original name, is ``core_storage_file_owner``.

``UNIQUE (store, sha256)`` is the dedup key, soft-deleted rows included: a re-registration of the
same bytes revives the marked file instead of storing a second copy. The row is immutable except
for ``deleted_at``; the cleanup task removes it with its bytes.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, CheckConstraint, Index, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from src.core.database import SoftDeleteMixin
from src.core.database.runtime import Base
from src.core.database.types import timestamp
from src.core.utils.date import utc_now
from src.modules.core_storage.constants import (
    CODE_LEN,
    EXTENSION_MAX,
    FILE_TYPES,
    MIME_MAX,
    SHA256_LEN,
    STORE_MAX,
    TYPE_MAX,
)

TYPE_CHECK = "type IN ({})".format(", ".join(f"'{value}'" for value in FILE_TYPES))


class CoreStorageFile(SoftDeleteMixin, Base):
    __tablename__ = "core_storage_file"
    __table_args__ = (
        UniqueConstraint("store", "sha256", name="uq_core_storage_file_store_sha256"),
        CheckConstraint(TYPE_CHECK, name="ck_core_storage_file_type"),
        # The cleanup task looks files up by how long ago they were marked.
        Index("ix_core_storage_file_deleted_at", "deleted_at"),
    )

    code: Mapped[str] = mapped_column(String(CODE_LEN), primary_key=True)
    store: Mapped[str] = mapped_column(String(STORE_MAX))
    sha256: Mapped[str] = mapped_column(String(SHA256_LEN))
    type: Mapped[str] = mapped_column(String(TYPE_MAX))
    size: Mapped[int] = mapped_column(BigInteger)
    mime: Mapped[str] = mapped_column(String(MIME_MAX))
    extension: Mapped[str] = mapped_column(String(EXTENSION_MAX))
    created_at: Mapped[datetime] = mapped_column(timestamp(), default=utc_now)


__all__ = ["TYPE_CHECK", "CoreStorageFile"]
