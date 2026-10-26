"""core/backup_inventory: what a copy says its tree of stored files holds, and how a tree is
compared with it. The restore and `backup --verify` paths over real copies are
`tests/core/test_restore.py`; this is the comparison itself, on a temp folder."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from src.core.backup_inventory import (
    DIFFERENCES_SHOWN,
    INVENTORY_NAME,
    Expected,
    InventoryUnusable,
    differences,
    expected_files,
    scan_tree,
    write_inventory,
)

pytestmark = pytest.mark.pure


def put(root: Path, relative: str, content: bytes) -> None:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)


def storage_entry(directory: Path, files: dict[str, int]) -> dict[str, object]:
    return {
        "files": len(files),
        "bytes": sum(files.values()),
        "inventory": INVENTORY_NAME,
        "inventory_sha256": write_inventory(directory, files),
    }


def test_a_tree_is_scanned_by_the_rules_of_the_snapshot(tmp_path: Path):
    root = tmp_path / "storage"
    put(root, "public/AB/CD/ABCDEF0123.png", b"picture")
    put(root, "public/AB/CD/.ABCDEF0124.png.0f0f0f0f.part", b"half")
    (root / "empty").mkdir()
    (root / "public" / "pointer").symlink_to(root / "public/AB/CD/ABCDEF0123.png")

    assert scan_tree(root) == {"public/AB/CD/ABCDEF0123.png": 7}


def test_the_inventory_reads_back_as_written(tmp_path: Path):
    files = {"public/AB/CD/ABCDEF0123.png": 7, "private/12/34/1234567890": 0}

    expected = expected_files(tmp_path, storage_entry(tmp_path, files))

    assert expected == Expected(files=2, size=7, inventory=files)
    assert differences(expected, dict(files)) == []


def test_an_inventory_the_manifest_does_not_vouch_for_is_refused(tmp_path: Path):
    entry = storage_entry(tmp_path, {"a": 1})

    with pytest.raises(InventoryUnusable, match="sha256 differs"):
        expected_files(tmp_path, {**entry, "inventory_sha256": "0" * 64})


def test_an_inventory_that_disagrees_with_the_totals_is_refused(tmp_path: Path):
    entry = storage_entry(tmp_path, {"a": 1, "b": 2})

    with pytest.raises(InventoryUnusable, match="lists 2 file"):
        expected_files(tmp_path, {**entry, "files": 3})


@pytest.mark.parametrize("content", [b"not json", b"[1, 2]", b'{"a": -1}', b'{"a": true}'])
def test_an_inventory_that_is_no_list_of_sizes_is_refused(tmp_path: Path, content: bytes):
    (tmp_path / INVENTORY_NAME).write_bytes(content)
    entry = {
        "files": 1,
        "bytes": 1,
        "inventory": INVENTORY_NAME,
        "inventory_sha256": hashlib.sha256(content).hexdigest(),
    }

    with pytest.raises(InventoryUnusable):
        expected_files(tmp_path, entry)


def test_totals_that_are_no_counts_are_refused(tmp_path: Path):
    with pytest.raises(InventoryUnusable, match="not counts"):
        expected_files(tmp_path, {"files": "2", "bytes": 13})


def test_a_copy_without_an_inventory_is_held_to_its_totals(tmp_path: Path):
    expected = expected_files(tmp_path, {"files": 2, "bytes": 13})

    assert expected.inventory is None
    assert differences(expected, {"a": 7, "b": 6}) == []
    assert differences(expected, {"a": 7, "b": 6, "c": 0}) != []
    assert differences(expected, {"a": 7, "b": 5}) != []


def test_a_long_list_of_differences_is_cut_with_a_count(tmp_path: Path):
    recorded = {f"public/{index:04}": 1 for index in range(DIFFERENCES_SHOWN + 5)}
    expected = Expected(files=len(recorded), size=len(recorded), inventory=recorded)

    lines = differences(expected, {})

    assert lines[0] == f"missing: {DIFFERENCES_SHOWN + 5}"
    assert len(lines) == 1 + DIFFERENCES_SHOWN + 1
    assert lines[-1] == "  … and 5 more"


def test_the_inventory_file_is_sorted_json(tmp_path: Path):
    write_inventory(tmp_path, {"b": 2, "a": 1})

    assert list(json.loads((tmp_path / INVENTORY_NAME).read_text())) == ["a", "b"]
