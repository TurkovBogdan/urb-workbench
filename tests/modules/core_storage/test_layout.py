"""Where the bytes lie: the store list, the path of a file, the move into place."""

from __future__ import annotations

import errno
import os
from pathlib import Path

import pytest

from src.modules.core_storage import layout as layout_module
from src.modules.core_storage.errors import InvalidStores, UnknownStore
from src.modules.core_storage.layout import StorageLayout, get_layout, validate_stores

pytestmark = pytest.mark.pure


def test_a_valid_list_comes_back_as_a_tuple():
    assert validate_stores(["public", "private"]) == ("public", "private")


@pytest.mark.parametrize(
    "stores",
    [
        [],
        ["public", "public"],
        ["a/b"],
        ["..\\up"],
        [".."],
        [""],
        ["x" * 33],
        "public",
    ],
    ids=["empty", "repeated", "slash", "backslash", "dotdot", "blank", "too-long", "one-string"],
)
def test_an_unusable_list_is_refused(stores):
    with pytest.raises(InvalidStores):
        validate_stores(stores)


def test_the_path_follows_from_store_code_and_extension(tmp_path: Path):
    layout = StorageLayout(tmp_path / "storage", tmp_path / "tmp", ["public"])
    assert layout.file_path("public", "3F9A0C21BE", ".png") == (
        tmp_path / "storage" / "public" / "3F" / "9A" / "3F9A0C21BE.png"
    )


def test_a_store_off_the_list_still_has_a_path(tmp_path: Path):
    layout = StorageLayout(tmp_path / "storage", tmp_path / "tmp", ["public"])
    assert layout.file_path("archive", "3F9A0C21BE", "").parent.parent.parent.name == "archive"


def test_registration_needs_a_listed_store(tmp_path: Path):
    layout = StorageLayout(tmp_path / "storage", tmp_path / "tmp", ["public"])
    layout.require_store("public")
    with pytest.raises(UnknownStore):
        layout.require_store("private")


def test_ensure_dirs_creates_a_folder_per_store(tmp_path: Path):
    layout = StorageLayout(tmp_path / "storage", tmp_path / "tmp", ["public", "private"])
    layout.ensure_dirs()
    assert sorted(p.name for p in (tmp_path / "storage").iterdir()) == ["private", "public"]


def test_place_moves_the_file_and_creates_the_folders(tmp_path: Path):
    layout = StorageLayout(tmp_path / "storage", tmp_path / "tmp", ["public"])
    source = tmp_path / "incoming.bin"
    source.write_bytes(b"bytes")
    target = layout.file_path("public", "AABBCCDDEE", ".bin")

    layout.place(source, target)

    assert target.read_bytes() == b"bytes"
    assert not source.exists()


def test_place_across_file_systems_copies_next_to_the_target(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    layout = StorageLayout(tmp_path / "storage", tmp_path / "tmp", ["public"])
    source = tmp_path / "incoming.bin"
    source.write_bytes(b"bytes")
    target = layout.file_path("public", "AABBCCDDEE", ".bin")
    real_replace = os.replace
    calls: list[tuple[Path, Path]] = []

    def replace(src, dst):
        calls.append((Path(src), Path(dst)))
        if Path(src) == source:
            raise OSError(errno.EXDEV, "Invalid cross-device link")
        real_replace(src, dst)

    monkeypatch.setattr(layout_module.os, "replace", replace)

    layout.place(source, target)

    assert target.read_bytes() == b"bytes"
    assert calls[-1][0].parent == target.parent and calls[-1][0].name.endswith(".part")
    assert list(target.parent.glob("*.part")) == []


def test_place_passes_other_errors_through(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    layout = StorageLayout(tmp_path / "storage", tmp_path / "tmp", ["public"])
    source = tmp_path / "incoming.bin"
    source.write_bytes(b"bytes")

    def replace(src, dst):
        raise OSError(errno.EACCES, "Permission denied")

    monkeypatch.setattr(layout_module.os, "replace", replace)
    with pytest.raises(OSError):
        layout.place(source, layout.file_path("public", "AABBCCDDEE", ".bin"))
    assert source.exists()


def test_place_survives_the_cleanup_pruning_the_folder_it_just_made(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    """The cleanup runs in another process and removes folders it emptied. A registration that
    made the folder a moment earlier must still land its file, not fail on a vanished folder."""
    layout = StorageLayout(tmp_path / "storage", tmp_path / "tmp", ["public"])
    source = tmp_path / "incoming.bin"
    source.write_bytes(b"bytes")
    target = layout.file_path("public", "AABBCCDDEE", ".bin")
    real_replace = os.replace
    pruned: list[Path] = []

    def replace(src, dst):
        if not pruned:
            layout.prune(target)
            pruned.append(target.parent)
            assert not target.parent.exists()
        real_replace(src, dst)

    monkeypatch.setattr(layout_module.os, "replace", replace)

    layout.place(source, target)

    assert pruned and target.read_bytes() == b"bytes"


def test_place_of_a_vanished_source_gives_up(tmp_path: Path):
    layout = StorageLayout(tmp_path / "storage", tmp_path / "tmp", ["public"])
    with pytest.raises(FileNotFoundError):
        layout.place(tmp_path / "gone.bin", layout.file_path("public", "AABBCCDDEE", ".bin"))


def test_prune_removes_empty_folders_up_to_the_store(tmp_path: Path):
    layout = StorageLayout(tmp_path / "storage", tmp_path / "tmp", ["public"])
    target = layout.file_path("public", "AABBCCDDEE", ".bin")
    target.parent.mkdir(parents=True)

    layout.prune(target)

    assert not (layout.store_dir("public") / "AA").exists()
    assert layout.store_dir("public").is_dir()


def test_prune_keeps_a_folder_with_a_file_and_takes_a_missing_one_quietly(tmp_path: Path):
    layout = StorageLayout(tmp_path / "storage", tmp_path / "tmp", ["public"])
    neighbour = layout.file_path("public", "AABB000001", ".bin")
    neighbour.parent.mkdir(parents=True)
    neighbour.write_bytes(b"kept")

    layout.prune(layout.file_path("public", "AABB000002", ".bin"))
    layout.prune(layout.file_path("public", "FFEE000001", ".bin"))

    assert neighbour.read_bytes() == b"kept"


def test_the_layout_is_unset_until_the_module_configures_it(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(layout_module, "_layout", None)
    with pytest.raises(RuntimeError):
        get_layout()
