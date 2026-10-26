"""The archive container: a zip with a recognising first entry, written and read under limits.

What makes the archive a format of its own is its layout and its manifest, not the way the bytes
are packed — so the container is the standard library's zip. A renamed zip is told apart by the
first entry, ``mimetype``, stored **uncompressed**: the signature sits at a fixed offset from the
start of the file, and the type is known by the content, not by the extension.

The reader takes the archive as untrusted. Entry names are checked against the layout the
consumer declared (``ArchiveFormat.entries``), the size is counted while reading — the zip header
is part of the same file and proves nothing — and the sums are checked against the manifest.
Checks go cheapest first: the container, the names, the manifest, then every byte.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import re
import zipfile
from collections.abc import AsyncIterator, Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from src.core.utils.date import datetime_to_agent, utc_now
from src.modules.core_transfer.constants import (
    MANIFEST_ENTRY,
    MAX_TEXT_ENTRY_BYTES,
    MAX_TOTAL_UNCOMPRESSED_BYTES,
    MIMETYPE_ENTRY,
    READ_CHUNK,
)
from src.modules.core_transfer.errors import (
    ARCHIVE_TOO_LARGE,
    ENTRY_DAMAGED,
    ENTRY_NOT_ALLOWED,
    INVENTORY_MISMATCH,
    MANIFEST_INVALID,
    NOT_ARCHIVE,
    TransferError,
)
from src.modules.core_transfer.manifest import (
    Manifest,
    ManifestFile,
    ManifestRoot,
    ManifestSource,
    manifest_bytes,
    parse_manifest,
)

_MB = 1024 * 1024


@dataclass(frozen=True)
class ArchiveFormat:
    """What one kind of archive looks like — declared by its consumer.

    ``entries`` — patterns of every entry name the format writes besides ``mimetype`` and
    ``manifest.json``. ``file_directory`` — the folder of stored files' bytes: those entries are
    held to the storage's ceiling, every other one to the text limit.
    """

    media_type: str
    name: str
    version: int
    extension: str
    entries: tuple[re.Pattern[str], ...]
    file_directory: str = "files/"


class ArchiveWriter:
    """The writing side: entries go to the file one by one, their sums counted on the way.

    The manifest goes last — it lists the sums of every entry, and they are not known before the
    entries are written. The order of entries does not matter to the reader (it takes them by name
    through the central directory); only the first one, the recognising one, does.
    """

    def __init__(self, path: Path, fmt: ArchiveFormat) -> None:
        self._fmt = fmt
        self._zip = zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED, allowZip64=True)
        self._files: list[ManifestFile] = []
        self._zip.writestr(
            zipfile.ZipInfo(MIMETYPE_ENTRY), fmt.media_type, compress_type=zipfile.ZIP_STORED
        )

    def __enter__(self) -> "ArchiveWriter":
        return self

    def __exit__(self, *_exc: object) -> None:
        self._zip.close()

    def add_rows(self, entry: str, rows: Iterable[dict[str, Any]]) -> None:
        payload = "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows)
        self.add_text(entry, payload)

    def add_text(self, entry: str, text: str) -> None:
        payload = text.encode("utf-8")
        self._zip.writestr(entry, payload)
        self._files.append(
            ManifestFile(path=entry, bytes=len(payload), sha256=hashlib.sha256(payload).hexdigest())
        )

    def add_file(self, entry: str, source: Path) -> None:
        """Copy a file into the archive as a stream, counting its sum on the way."""
        digest = hashlib.sha256()
        size = 0
        with source.open("rb") as reading, self._zip.open(entry, "w", force_zip64=True) as writing:
            for chunk in iter(lambda: reading.read(READ_CHUNK), b""):
                digest.update(chunk)
                size += len(chunk)
                writing.write(chunk)
        self._files.append(ManifestFile(path=entry, bytes=size, sha256=digest.hexdigest()))

    def finish(
        self,
        *,
        archive_id: str,
        source: ManifestSource,
        root: ManifestRoot,
        counts: dict[str, int],
        dangling_refs: list[str],
    ) -> Manifest:
        manifest = Manifest(
            format=self._fmt.name,
            format_version=self._fmt.version,
            archive_id=archive_id,
            created_at=datetime_to_agent(utc_now()),
            source=source,
            root=root,
            counts=counts,
            files=self._files,
            dangling_refs=dangling_refs,
        )
        self._zip.writestr(MANIFEST_ENTRY, manifest_bytes(manifest))
        return manifest


class ArchiveReader:
    """The reading side: the checks as a ladder, then reading entries by name.

    ``max_file_bytes`` — the ceiling of an entry under the format's file folder: the storage of
    THIS installation, which would refuse a larger file anyway — better before the import than in
    the middle of it.
    """

    def __init__(self, path: Path, fmt: ArchiveFormat, *, max_file_bytes: int) -> None:
        self.path = path
        self.fmt = fmt
        self._max_file_bytes = max_file_bytes
        self._zip: zipfile.ZipFile | None = None
        self._names: set[str] = set()
        self.manifest: Manifest | None = None

    def __enter__(self) -> "ArchiveReader":
        if not zipfile.is_zipfile(self.path):
            raise TransferError(NOT_ARCHIVE, f"Not a {self.fmt.extension} archive")
        try:
            self._zip = zipfile.ZipFile(self.path)
        except zipfile.BadZipFile as error:
            raise TransferError(NOT_ARCHIVE, f"Not a {self.fmt.extension} archive") from error
        self._names = set(self._zip.namelist())
        return self

    def __exit__(self, *_exc: object) -> None:
        if self._zip is not None:
            self._zip.close()

    def open_manifest(self) -> Manifest:
        """Recognise the container and parse the manifest — all done before reading the content."""
        archive = self._archive
        infos = archive.infolist()
        if not infos or infos[0].filename != MIMETYPE_ENTRY:
            raise TransferError(NOT_ARCHIVE, f"Not a {self.fmt.extension} archive")
        if self._read(MIMETYPE_ENTRY, MAX_TEXT_ENTRY_BYTES).decode("utf-8", "replace").strip() != self.fmt.media_type:
            raise TransferError(NOT_ARCHIVE, f"Not a {self.fmt.extension} archive")
        for info in infos:
            if not self._allowed(info.filename):
                raise TransferError(
                    ENTRY_NOT_ALLOWED,
                    f"The archive holds an entry this format never writes: {info.filename!r}",
                    params={"name": info.filename},
                )
        if sum(info.file_size for info in infos) > MAX_TOTAL_UNCOMPRESSED_BYTES:
            raise TransferError(
                ARCHIVE_TOO_LARGE,
                "The archive is over the unpacking limit",
                params={"limit_mb": MAX_TOTAL_UNCOMPRESSED_BYTES // _MB},
            )
        if MANIFEST_ENTRY not in self._names:
            raise TransferError(MANIFEST_INVALID, "The archive has no manifest")
        self.manifest = parse_manifest(
            self._read(MANIFEST_ENTRY, MAX_TEXT_ENTRY_BYTES),
            format_name=self.fmt.name,
            supported_version=self.fmt.version,
        )
        return self.manifest

    def verify_inventory(self) -> None:
        """Every entry the manifest promises is here byte for byte, and nothing else is."""
        manifest = self._require_manifest()
        present = self._names - {MIMETYPE_ENTRY, MANIFEST_ENTRY}
        promised = {item.path for item in manifest.files}
        if promised != present:
            missing = sorted(promised - present)
            extra = sorted(present - promised)
            raise TransferError(
                INVENTORY_MISMATCH,
                f"The archive differs from its manifest (missing: {missing}; extra: {extra})",
                params={"missing": ", ".join(missing) or "—", "extra": ", ".join(extra) or "—"},
            )
        for item in manifest.files:
            digest = hashlib.sha256()
            size = 0
            for chunk in self._chunks(item.path):
                digest.update(chunk)
                size += len(chunk)
            if size != item.bytes or digest.hexdigest() != item.sha256:
                raise TransferError(
                    ENTRY_DAMAGED,
                    f"The entry {item.path!r} was damaged on the way",
                    params={"name": item.path},
                )

    def has(self, entry: str) -> bool:
        return entry in self._names

    def inventory_of(self, entry: str) -> ManifestFile | None:
        """The manifest's line of an entry — its size and sha256, checked against the bytes by
        ``verify_inventory``. What a row SAYS about a file is trusted only where it matches this."""
        manifest = self._require_manifest()
        return next((item for item in manifest.files if item.path == entry), None)

    def rows(self, entry: str) -> list[dict[str, Any]]:
        if entry not in self._names:
            return []
        payload = self._read(entry, MAX_TEXT_ENTRY_BYTES).decode("utf-8")
        # Split strictly on ``\n``: ``splitlines`` also breaks on Unicode separators (U+2028,
        # U+0085 and kin), which live texts carry and JSON keeps as they are.
        try:
            return [json.loads(line) for line in payload.split("\n") if line.strip()]
        except json.JSONDecodeError as error:
            raise TransferError(
                ENTRY_DAMAGED, f"The entry {entry!r} is not JSON lines", params={"name": entry}
            ) from error

    def text(self, entry: str) -> str:
        if entry not in self._names:
            return ""
        return self._read(entry, MAX_TEXT_ENTRY_BYTES).decode("utf-8")

    async def file_chunks(self, entry: str) -> AsyncIterator[bytes]:
        """The bytes of a file entry as a stream — what ``core_storage.file_spool`` takes."""
        stream = self._archive.open(entry)
        read = 0
        try:
            while chunk := await asyncio.to_thread(stream.read, READ_CHUNK):
                read += len(chunk)
                if read > self._limit_of(entry):
                    raise TransferError(ENTRY_DAMAGED, f"The entry {entry!r} is over its limit", params={"name": entry})
                yield chunk
        finally:
            stream.close()

    def _allowed(self, name: str) -> bool:
        if name in (MIMETYPE_ENTRY, MANIFEST_ENTRY):
            return True
        return any(pattern.fullmatch(name) for pattern in self.fmt.entries)

    def _limit_of(self, entry: str) -> int:
        return self._max_file_bytes if entry.startswith(self.fmt.file_directory) else MAX_TEXT_ENTRY_BYTES

    def _chunks(self, entry: str) -> Iterable[bytes]:
        limit = self._limit_of(entry)
        read = 0
        with self._archive.open(entry) as stream:
            for chunk in iter(lambda: stream.read(READ_CHUNK), b""):
                read += len(chunk)
                if read > limit:
                    raise TransferError(
                        ARCHIVE_TOO_LARGE,
                        f"The entry {entry!r} is over the unpacking limit",
                        params={"limit_mb": limit // _MB},
                    )
                yield chunk

    def _read(self, entry: str, limit: int) -> bytes:
        chunks: list[bytes] = []
        read = 0
        with self._archive.open(entry) as stream:
            for chunk in iter(lambda: stream.read(READ_CHUNK), b""):
                read += len(chunk)
                if read > limit:
                    raise TransferError(
                        ARCHIVE_TOO_LARGE,
                        f"The entry {entry!r} is over the unpacking limit",
                        params={"limit_mb": limit // _MB},
                    )
                chunks.append(chunk)
        return b"".join(chunks)

    @property
    def _archive(self) -> zipfile.ZipFile:
        if self._zip is None:
            raise TransferError(NOT_ARCHIVE, "The archive is not open")
        return self._zip

    def _require_manifest(self) -> Manifest:
        return self.manifest if self.manifest is not None else self.open_manifest()


__all__ = ["ArchiveFormat", "ArchiveReader", "ArchiveWriter"]
