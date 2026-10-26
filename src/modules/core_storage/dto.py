"""What the storage hands out: plain frozen values, never ORM rows."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from src.modules.core_storage.constants import OWNER_ID_MAX, OWNER_KEY_MAX, OWNER_TYPE_MAX
from src.modules.core_storage.models import CoreStorageFile, CoreStorageFileOwner


@dataclass(frozen=True)
class Owner:
    """Who holds a file: the consumer's entity and the place in it (``''`` — the whole entity).

    Checked on construction: SQLite stores a value longer than its column and PostgreSQL refuses
    it, so a width left unchecked here works on one provider and breaks on the other.
    """

    type: str
    id: str
    key: str = ""

    def __post_init__(self) -> None:
        for field, value, limit, required in (
            ("type", self.type, OWNER_TYPE_MAX, True),
            ("id", self.id, OWNER_ID_MAX, True),
            ("key", self.key, OWNER_KEY_MAX, False),
        ):
            if not isinstance(value, str):
                raise ValueError(f"Owner {field} must be a string, got {type(value).__name__}")
            if required and not value:
                raise ValueError(f"Owner {field} is empty — an owner names the entity holding the file")
            if len(value) > limit:
                raise ValueError(f"Owner {field} is {len(value)} characters, over the {limit} the column holds")


@dataclass(frozen=True)
class FileOwner:
    """One place holding a file, and the name the file came there under.

    ``owner`` is the key ``file_release`` takes. ``original_filename + original_extension`` is
    the name exactly as the owner brought it, ``''`` when it brought none — to show the file
    and to hand it out under its name.
    """

    owner: Owner
    original_filename: str
    original_extension: str
    created_at: datetime
    deleted_at: datetime | None


@dataclass(frozen=True)
class HeldFile:
    """One live place: which file, held by which owner — what a consumer reconciles its own
    bindings against."""

    file_code: str
    owner: Owner


@dataclass(frozen=True)
class StoredFile:
    """The bytes and what they are; the names they were brought under are per place, ``FileOwner``."""

    code: str
    store: str
    sha256: str
    type: str
    size: int
    mime: str
    extension: str
    created_at: datetime
    deleted_at: datetime | None


@dataclass(frozen=True)
class SpooledFile:
    """A stream written to the module's temporary file by ``file_spool``, counted on the way in:
    ``file_register_spooled`` takes it without reading the bytes again. ``head`` — the first bytes,
    what the type is recognised by."""

    path: Path
    sha256: str
    size: int
    head: bytes


def stored_file(row: CoreStorageFile) -> StoredFile:
    return StoredFile(
        code=row.code,
        store=row.store,
        sha256=row.sha256,
        type=row.type,
        size=row.size,
        mime=row.mime,
        extension=row.extension,
        created_at=row.created_at,
        deleted_at=row.deleted_at,
    )


def file_owner(row: CoreStorageFileOwner) -> FileOwner:
    return FileOwner(
        owner=Owner(type=row.owner_type, id=row.owner_id, key=row.owner_key),
        original_filename=row.original_filename,
        original_extension=row.original_extension,
        created_at=row.created_at,
        deleted_at=row.deleted_at,
    )


__all__ = [
    "FileOwner",
    "HeldFile",
    "Owner",
    "SpooledFile",
    "StoredFile",
    "file_owner",
    "stored_file",
]
