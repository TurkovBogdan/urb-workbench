"""Where the bytes lie: the storage root, the stores in it, the path of a file, the move into place.

The root comes from the core config (``Config.storage_root``: ``STORAGE_PATH``, by default
``AppPath.storage``), the temporary directory from the core too (``AppPath.tmp``), the store list
from the module's constructor. A store is a folder inside the root, named by its code. A path is
built from these and the file row only — a path from the caller would let it write anywhere.

The module's temporary files are named here as well (``temp_file``, the cross-device copy in
``_move``), so the cleanup can tell them from anything else lying in ``tmp`` (``stale_temporaries``).
"""

from __future__ import annotations

import errno
import os
import shutil
from collections.abc import Sequence
from pathlib import Path

from src.core.utils.hashing import random_hash
from src.modules.core_storage.constants import (
    PLACE_ATTEMPTS,
    STORE_MAX,
    TEMP_PREFIX,
    TEMP_SUFFIX,
)
from src.modules.core_storage.errors import InvalidStores, UnknownStore


def validate_stores(stores: Sequence[str]) -> tuple[str, ...]:
    """The store list as a tuple; empty, repeated or a code that is not one folder name — refused."""
    if isinstance(stores, str):
        raise InvalidStores("The store list is a sequence of codes, not one string")
    codes = tuple(stores)
    if not codes:
        raise InvalidStores("The store list is empty — the storage has nowhere to put a file")
    if len(set(codes)) != len(codes):
        raise InvalidStores(f"The store list repeats a code: {codes}")
    for code in codes:
        single_segment = (
            isinstance(code, str)
            and code not in ("", ".", "..")
            and Path(code).name == code
            and "/" not in code
            and "\\" not in code
        )
        if not single_segment:
            raise InvalidStores(f"Store code {code!r} must be one folder name, not a path")
        if len(code) > STORE_MAX:
            raise InvalidStores(f"Store code {code!r} is longer than {STORE_MAX} characters")
    return codes


class StorageLayout:
    """``root_shared`` — the root is likely another base's too (``module.root_may_be_shared``):
    the scheduled reconciliation then deletes nothing."""

    def __init__(
        self, root: Path, tmp: Path, stores: Sequence[str], *, root_shared: bool = False
    ) -> None:
        self.root = root
        self.tmp = tmp
        self.stores = validate_stores(stores)
        self.root_shared = root_shared

    def store_dir(self, store: str) -> Path:
        return self.root / store

    def file_path(self, store: str, code: str, extension: str) -> Path:
        """``<root>/<store>/<C[0:2]>/<C[2:4]>/<C><ext>``.

        The list is not consulted: the files of a store taken off the list stay readable and the
        cleanup still removes them.
        """
        return self.root / store / code[0:2] / code[2:4] / f"{code}{extension}"

    def require_store(self, store: str) -> None:
        if store not in self.stores:
            raise UnknownStore(store, self.stores)

    def place(self, temp_file: Path, target: Path) -> None:
        """Move ``temp_file`` to ``target``: the file appears there whole or not at all."""
        for attempt in range(PLACE_ATTEMPTS):
            target.parent.mkdir(parents=True, exist_ok=True)
            try:
                self._move(temp_file, target)
                return
            except FileNotFoundError:
                # The cleanup in another process prunes the folders it empties, and the one made
                # here a moment ago may already be gone; a vanished source is a real failure.
                if not temp_file.exists() or attempt == PLACE_ATTEMPTS - 1:
                    raise

    def prune(self, removed_file: Path) -> None:
        """Remove the folders ``<C[0:2]>/<C[2:4]>`` left empty by a removed file; the store stays."""
        for folder in (removed_file.parent, removed_file.parent.parent):
            try:
                folder.rmdir()
            except FileNotFoundError:
                continue
            except OSError:
                return

    def _move(self, temp_file: Path, target: Path) -> None:
        """``replace`` cannot cross file systems, and the temporary directory and the storage root
        may lie on different disks. Then the bytes are first copied under a temporary name next
        to the target, and that name is what ``replace`` moves into place.
        """
        try:
            os.replace(temp_file, target)
            return
        except OSError as exc:
            if exc.errno != errno.EXDEV:
                raise
        part = target.with_name(f".{target.name}.{random_hash(8)}{TEMP_SUFFIX}")
        try:
            shutil.copyfile(temp_file, part)
            os.replace(part, target)
        finally:
            part.unlink(missing_ok=True)

    def temp_file(self) -> Path:
        """A fresh name for a temporary file of the module in ``tmp``, the folder made."""
        self.tmp.mkdir(parents=True, exist_ok=True)
        return self.tmp / f"{TEMP_PREFIX}{random_hash(16)}{TEMP_SUFFIX}"

    def stale_temporaries(self, before: float) -> list[Path]:
        """The module's temporary files last written before ``before`` (a ``time.time()``): spools
        in ``tmp`` and cross-device copies inside the stores — whatever a process left when it
        died midway. Anything else in ``tmp`` is someone else's and is not listed."""
        found = list(self.tmp.glob(f"{TEMP_PREFIX}*{TEMP_SUFFIX}")) if self.tmp.is_dir() else []
        for store in self.stores:
            folder = self.store_dir(store)
            if folder.is_dir():
                found.extend(folder.glob(f"*/*/.*{TEMP_SUFFIX}"))
        return [path for path in found if written_before(path, before)]

    def lying_in(self, store: str) -> list[Path]:
        """What lies at the depth of stored bytes in a store — ``<C[0:2]>/<C[2:4]>/<name>`` —
        except dot-files, which are temporaries in flight. Whether a name is a file's bytes is
        the caller's question."""
        folder = self.store_dir(store)
        if not folder.is_dir():
            return []
        return sorted(
            path for path in folder.glob("*/*/*") if path.is_file() and not path.name.startswith(".")
        )

    def ensure_dirs(self) -> None:
        for store in self.stores:
            self.store_dir(store).mkdir(parents=True, exist_ok=True)


def written_before(path: Path, before: float) -> bool:
    """A file last written before ``before`` (a ``time.time()``); a vanished one is not."""
    try:
        return path.is_file() and path.stat().st_mtime < before
    except OSError:
        return False


_layout: StorageLayout | None = None


def set_layout(layout: StorageLayout) -> None:
    global _layout
    _layout = layout


def get_layout() -> StorageLayout:
    if _layout is None:
        raise RuntimeError("core_storage: the layout is not set — the module was not configured")
    return _layout


__all__ = ["StorageLayout", "get_layout", "set_layout", "validate_stores", "written_before"]
