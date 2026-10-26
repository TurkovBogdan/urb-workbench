"""The stored files a copy holds, by name and size — and the check of a tree against them.

`backup` links every file of the storage root into the copy and knows each one as it goes; the
inventory (`inventory.json`, beside `backup.json`) keeps that knowledge: the path of every file
inside `storage/` and its size. A copy never changes once taken, so a tree that differs from its
inventory was changed afterwards — a file deleted by hand, a disk that lost blocks — and restoring
it would bring back rows whose bytes are gone. `restore` checks the tree it prepared before it
swaps anything in; `backup --verify` checks a copy without restoring it.

**Sizes, not hashes.** A hash per file would read every stored byte at every update, and buy
little: a link shares its bytes with the live store, so bytes rotten in the copy are rotten there
too, with nothing to restore them from. Content against the rows' own hashes is `storage check
--sha` after the restore.

**One rule: the tree matches exactly.** A missing file and a file of another size are damage. An
extra file harms no row, but it says the copy was written to after it was taken, and the command
cannot tell an addition from a substitution — so it is refused too, named.

**The manifest vouches for the inventory**: `backup.json` records its sha256, so an inventory
replaced or damaged after the copy was taken is refused rather than trusted. A copy taken before
the inventory existed carries only its totals (`storage.files`, `storage.bytes`); its tree is
checked against those, which catches a loss without naming the file.
"""

from __future__ import annotations

import errno
import hashlib
import json
import os
import stat
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

INVENTORY_NAME = "inventory.json"
# A file still being written — a spool, a copy across disks — is no one's bytes yet.
PARTIAL_SUFFIX = ".part"
DIFFERENCES_SHOWN = 20


class InventoryUnusable(RuntimeError):
    """The inventory is missing, unreadable or not the one the manifest vouches for."""


@dataclass(frozen=True)
class Expected:
    """What the tree of a copy must hold: every file by name and size, or — a copy older than
    the inventory — only how many files and how many bytes."""

    files: int
    size: int
    inventory: Mapping[str, int] | None = None

    def describe(self) -> str:
        if self.inventory is None:
            return (
                f"the totals its manifest records ({self.files} file(s), {self.size} byte(s)) — "
                "a copy without an inventory"
            )
        return f"every file as its inventory records ({self.files} file(s))"


def write_inventory(directory: Path, files: Mapping[str, int]) -> str:
    """Write the inventory into the copy; answers its sha256, which the manifest records."""
    content = json.dumps(dict(sorted(files.items())), indent=0).encode("utf-8")
    (directory / INVENTORY_NAME).write_bytes(content)
    return hashlib.sha256(content).hexdigest()


def expected_files(directory: Path, storage: Mapping[str, object]) -> Expected:
    """What the manifest's ``storage`` entry promises about ``directory/storage/``."""
    files, size = storage["files"], storage["bytes"]
    if not _is_count(files) or not _is_count(size):
        raise InventoryUnusable(
            f"storage.files and storage.bytes are not counts: {files!r}, {size!r}"
        )
    name = storage.get("inventory")
    if name is None:
        return Expected(files=files, size=size)
    inventory = _read_inventory(directory / str(name), str(storage.get("inventory_sha256")))
    if len(inventory) != files or sum(inventory.values()) != size:
        raise InventoryUnusable(
            f"{name} lists {len(inventory)} file(s), {sum(inventory.values())} byte(s); "
            f"the manifest records {files} file(s), {size} byte(s)"
        )
    return Expected(files=files, size=size, inventory=inventory)


class NotARegularFile(OSError):
    """What `read_regular_file` raises for a FIFO, a device or a folder."""


def read_regular_file(path: Path) -> bytes:
    """The bytes of a copy's own file, refused unless it is a regular file: a FIFO under its name
    would make the read wait for a writer forever, a device would never end. Opened without
    blocking, so the refusal comes before any wait."""
    descriptor = os.open(path, os.O_RDONLY | os.O_NONBLOCK)
    with os.fdopen(descriptor, "rb") as file:
        if not stat.S_ISREG(os.fstat(file.fileno()).st_mode):
            raise NotARegularFile(errno.EINVAL, "not a regular file", str(path))
        return file.read()


def _read_inventory(path: Path, sha256: str) -> dict[str, int]:
    try:
        content = read_regular_file(path)
    except FileNotFoundError:
        raise InventoryUnusable(f"the inventory of the stored files is missing: {path}") from None
    except OSError as failure:
        raise InventoryUnusable(f"{path} cannot be read: {failure}") from failure
    if hashlib.sha256(content).hexdigest() != sha256:
        raise InventoryUnusable(
            f"{path} is not the inventory the manifest vouches for — its sha256 differs"
        )
    try:
        inventory = json.loads(content)
    except (ValueError, RecursionError) as failure:
        raise InventoryUnusable(f"{path} cannot be read: {failure}") from failure
    if not isinstance(inventory, dict) or not all(
        isinstance(name, str) and _is_count(size) for name, size in inventory.items()
    ):
        raise InventoryUnusable(f"{path} is not a list of files and their sizes")
    return inventory


def _is_count(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value >= 0


def scan_tree(root: Path) -> dict[str, int]:
    """What a snapshot of ``root`` holds, by the rules `snapshot_tree` takes files by: regular
    files only, no symbolic links, no half-written temporaries. Path inside ``root`` → size.

    A file or folder that cannot be read is left out, so it counts as missing: a copy whose
    bytes cannot be read cannot be restored either."""
    found: dict[str, int] = {}
    for folder, _subfolders, names in os.walk(root):
        here = Path(folder)
        for name in names:
            path = here / name
            try:
                if name.endswith(PARTIAL_SUFFIX) or path.is_symlink() or not path.is_file():
                    continue
                found[path.relative_to(root).as_posix()] = path.stat().st_size
            except OSError:
                continue
    return found


def differences(expected: Expected, found: Mapping[str, int]) -> list[str]:
    """How the tree differs from what the copy recorded, as report lines; empty — it matches."""
    if expected.inventory is None:
        total = sum(found.values())
        if (len(found), total) == (expected.files, expected.size):
            return []
        return [
            f"the tree holds {len(found)} file(s), {total} byte(s); the manifest records "
            f"{expected.files} file(s), {expected.size} byte(s). The copy has no inventory, so "
            "the files themselves cannot be named"
        ]
    recorded = expected.inventory
    missing = sorted(recorded.keys() - found.keys())
    resized = sorted(
        name for name in recorded.keys() & found.keys() if recorded[name] != found[name]
    )
    unexpected = sorted(found.keys() - recorded.keys())
    return [
        *_listed("missing", [f"{_shown(name)} ({recorded[name]} bytes)" for name in missing]),
        *_listed(
            "size not as recorded",
            [
                f"{_shown(name)} (recorded {recorded[name]} bytes, found {found[name]})"
                for name in resized
            ],
        ),
        *_listed(
            "not in the inventory",
            [f"{_shown(name)} ({found[name]} bytes)" for name in unexpected],
        ),
    ]


def _shown(name: str) -> str:
    """A name fit to print: bytes that are no UTF-8 (a hand-made file, say) are escaped, not
    left to break the report."""
    return name.encode("utf-8", "backslashreplace").decode("utf-8")


def _listed(kind: str, items: list[str]) -> list[str]:
    if not items:
        return []
    hidden = len(items) - DIFFERENCES_SHOWN
    return [
        f"{kind}: {len(items)}",
        *(f"  {item}" for item in items[:DIFFERENCES_SHOWN]),
        *([f"  … and {hidden} more"] if hidden > 0 else []),
    ]


__all__ = [
    "DIFFERENCES_SHOWN",
    "INVENTORY_NAME",
    "PARTIAL_SUFFIX",
    "Expected",
    "InventoryUnusable",
    "NotARegularFile",
    "differences",
    "expected_files",
    "read_regular_file",
    "scan_tree",
    "write_inventory",
]
