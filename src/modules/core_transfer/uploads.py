"""An uploaded archive in a temporary folder: taken in, found by its id, swept away.

The file lives between three requests (upload → analysis → apply), so it needs a place on disk and
a name nobody can forge. The name is the upload's id, not what the browser sent: the person's
string never gets into a path. The browser's name is kept beside it, to show on the plan.

Each consumer has its own folder (``tmp/transfer/<consumer>/``): an upload of a task archive is
not found by the codex's routes.
"""

from __future__ import annotations

import json
import re
import time
from collections.abc import AsyncIterable
from dataclasses import dataclass
from pathlib import Path

from ulid import ULID

from src.core.app_path import AppPath
from src.modules.core_transfer.constants import MAX_UPLOAD_BYTES, UPLOAD_LIFETIME_SECONDS
from src.modules.core_transfer.errors import ARCHIVE_TOO_LARGE, UPLOAD_NOT_FOUND, TransferError

_UPLOAD_ID = re.compile(r"^[0-9A-HJKMNP-TV-Z]{26}$")
_MB = 1024 * 1024
_NAME_MAX = 255


def transfer_root() -> Path:
    """The runtime folder of every consumer's uploads and exports; a test points it elsewhere."""
    return AppPath.from_root().tmp / "transfer"


@dataclass(frozen=True)
class StoredUpload:
    upload_id: str
    file_name: str
    size: int
    path: Path


class UploadArea:
    """One consumer's uploads and exports on disk."""

    def __init__(self, consumer: str, extension: str) -> None:
        self.consumer = consumer
        self.extension = extension

    def _folder(self, kind: str) -> Path:
        folder = transfer_root() / self.consumer / kind
        folder.mkdir(parents=True, exist_ok=True)
        return folder

    async def take(self, chunks: AsyncIterable[bytes], file_name: str) -> StoredUpload:
        """Write the body to the folder, counting its size as it comes."""
        self.sweep()
        upload_id = str(ULID())
        path = self._folder("import") / f"{upload_id}{self.extension}"
        written = 0
        try:
            with path.open("wb") as target:
                async for chunk in chunks:
                    written += len(chunk)
                    if written > MAX_UPLOAD_BYTES:
                        raise TransferError(
                            ARCHIVE_TOO_LARGE,
                            "The file is over the upload limit",
                            params={"limit_mb": MAX_UPLOAD_BYTES // _MB},
                        )
                    target.write(chunk)
        except BaseException:
            path.unlink(missing_ok=True)
            raise
        name = (file_name or path.name).strip()[:_NAME_MAX] or path.name
        self._passport(upload_id).write_text(
            json.dumps({"file_name": name, "size": written}, ensure_ascii=False), encoding="utf-8"
        )
        return StoredUpload(upload_id=upload_id, file_name=name, size=written, path=path)

    def get(self, upload_id: str) -> StoredUpload:
        """The upload by its id; an id of another shape is a miss, not a file search."""
        if not _UPLOAD_ID.match(upload_id or ""):
            raise TransferError(UPLOAD_NOT_FOUND, "Unknown upload")
        path = self._folder("import") / f"{upload_id}{self.extension}"
        if not path.is_file():
            raise TransferError(UPLOAD_NOT_FOUND, "The upload is not found or is removed already")
        passport = self._passport(upload_id)
        known = json.loads(passport.read_text(encoding="utf-8")) if passport.is_file() else {}
        return StoredUpload(
            upload_id=upload_id,
            file_name=str(known.get("file_name") or path.name),
            size=int(known.get("size") or path.stat().st_size),
            path=path,
        )

    def drop(self, upload_id: str) -> None:
        if not _UPLOAD_ID.match(upload_id or ""):
            return
        (self._folder("import") / f"{upload_id}{self.extension}").unlink(missing_ok=True)
        self._passport(upload_id).unlink(missing_ok=True)

    def sweep(self) -> None:
        """Throw away what abandoned imports and failed exports left more than a day ago."""
        deadline = time.time() - UPLOAD_LIFETIME_SECONDS
        for kind in ("import", "export"):
            for path in self._folder(kind).iterdir():
                if path.is_file() and path.stat().st_mtime < deadline:
                    path.unlink(missing_ok=True)

    def export_path(self) -> Path:
        """Where to build an archive before it is sent; the sender removes it afterwards."""
        self.sweep()
        return self._folder("export") / f"{ULID()}{self.extension}"

    def _passport(self, upload_id: str) -> Path:
        return self._folder("import") / f"{upload_id}.json"


def drop_file(path: Path) -> None:
    """Remove a sent archive — the response's background task."""
    path.unlink(missing_ok=True)


__all__ = ["StoredUpload", "UploadArea", "drop_file", "transfer_root"]
