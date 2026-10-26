"""The container: an archive of its own reads back; every way a hostile file is shaped is refused
by its own code, before a byte of content is trusted."""

from __future__ import annotations

import hashlib
import json
import zipfile
from pathlib import Path

import pytest

from src.modules.core_transfer import errors
from src.modules.core_transfer.container import ArchiveReader, ArchiveWriter
from src.modules.core_transfer.errors import TransferError
from src.modules.core_transfer.manifest import ManifestRoot, ManifestSource

from .conftest import FORMAT

pytestmark = pytest.mark.pure

LIMIT = 1024 * 1024


def _write(path: Path, *, rows=None, text: str = "body", payload: bytes = b"\x89PNG bytes") -> Path:
    source = path.parent / "payload.bin"
    source.write_bytes(payload)
    with ArchiveWriter(path, FORMAT) as archive:
        archive.add_rows("rows/items.jsonl", rows if rows is not None else [{"code": "0123456789", "title": "Т x"}])
        archive.add_text("texts/0123456789.md", text)
        archive.add_file("files/AAAAAAAAAA.png", source)
        archive.finish(
            archive_id="01J00000000000000000000000",
            source=ManifestSource(install_id="here", app_version="0.10.13"),
            root=ManifestRoot(code="0123456789", title="Задача"),
            counts={"items": 1},
            dangling_refs=["TASK@FFFFFFFFFF"],
        )
    return path


def _open(path: Path, *, max_file_bytes: int = LIMIT) -> ArchiveReader:
    return ArchiveReader(path, FORMAT, max_file_bytes=max_file_bytes)


def _rezip(source: Path, target: Path, *, drop: str | None = None, replace: dict[str, bytes] | None = None,
           add: dict[str, bytes] | None = None, first: str | None = None) -> Path:
    """Copy an archive entry by entry, changing what the case needs."""
    with zipfile.ZipFile(source) as old:
        names = old.namelist()
        if first is not None:
            names.remove(first)
            names.insert(0, first)
        with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as new:
            for name in names:
                if name == drop:
                    continue
                data = (replace or {}).get(name, old.read(name))
                compress = zipfile.ZIP_STORED if name == "mimetype" else zipfile.ZIP_DEFLATED
                new.writestr(zipfile.ZipInfo(name), data, compress_type=compress)
            for name, data in (add or {}).items():
                new.writestr(name, data)
    return target


def _refused(path: Path, code: str, *, verify: bool = True) -> TransferError:
    with pytest.raises(TransferError) as caught:
        with _open(path) as reader:
            reader.open_manifest()
            if verify:
                reader.verify_inventory()
    assert caught.value.code == code
    return caught.value


def test_an_archive_reads_back_as_written(tmp_path):
    path = _write(tmp_path / "a.tst")

    with _open(path) as reader:
        manifest = reader.open_manifest()
        reader.verify_inventory()
        rows = reader.rows("rows/items.jsonl")
        text = reader.text("texts/0123456789.md")

    assert manifest.root.code == "0123456789" and manifest.root.title == "Задача"
    assert manifest.dangling_refs == ["TASK@FFFFFFFFFF"]
    # A Unicode line separator inside a value does not split the row.
    assert rows == [{"code": "0123456789", "title": "Т x"}]
    assert text == "body"
    assert {item.path for item in manifest.files} == {
        "rows/items.jsonl", "texts/0123456789.md", "files/AAAAAAAAAA.png",
    }


def test_the_mimetype_entry_is_first_and_stored(tmp_path):
    path = _write(tmp_path / "a.tst")

    with zipfile.ZipFile(path) as archive:
        first = archive.infolist()[0]

    assert first.filename == "mimetype"
    assert first.compress_type == zipfile.ZIP_STORED


async def test_a_file_entry_streams_its_bytes(tmp_path):
    payload = b"x" * 700_000
    path = _write(tmp_path / "a.tst", payload=payload)

    with _open(path) as reader:
        reader.open_manifest()
        streamed = b"".join([chunk async for chunk in reader.file_chunks("files/AAAAAAAAAA.png")])

    assert hashlib.sha256(streamed).hexdigest() == hashlib.sha256(payload).hexdigest()


def test_not_a_zip_is_refused(tmp_path):
    path = tmp_path / "a.tst"
    path.write_bytes(b"plain text, not a zip")

    with pytest.raises(TransferError) as caught:
        with _open(path):
            pass

    assert caught.value.code == errors.NOT_ARCHIVE


def test_a_foreign_mimetype_is_refused(tmp_path):
    path = _rezip(_write(tmp_path / "a.tst"), tmp_path / "b.tst", replace={"mimetype": b"application/zip"})

    _refused(path, errors.NOT_ARCHIVE, verify=False)


def test_a_mimetype_that_is_not_first_is_refused(tmp_path):
    path = _rezip(_write(tmp_path / "a.tst"), tmp_path / "b.tst", first="manifest.json")

    _refused(path, errors.NOT_ARCHIVE, verify=False)


@pytest.mark.parametrize("name", ["../evil.md", "texts/../../x.md", "rows/other.jsonl", "texts/lower00000.md"])
def test_an_entry_the_format_never_writes_is_refused(tmp_path, name):
    path = _rezip(_write(tmp_path / "a.tst"), tmp_path / "b.tst", add={name: b"x"})

    error = _refused(path, errors.ENTRY_NOT_ALLOWED, verify=False)

    assert error.params["name"] == name


def test_no_manifest_is_refused(tmp_path):
    path = _rezip(_write(tmp_path / "a.tst"), tmp_path / "b.tst", drop="manifest.json")

    _refused(path, errors.MANIFEST_INVALID, verify=False)


def test_a_manifest_of_another_format_is_refused(tmp_path):
    original = _write(tmp_path / "a.tst")
    with zipfile.ZipFile(original) as archive:
        manifest = json.loads(archive.read("manifest.json"))
    manifest["format"] = "uroboros.codex"
    path = _rezip(original, tmp_path / "b.tst", replace={"manifest.json": json.dumps(manifest).encode()})

    _refused(path, errors.FOREIGN_FORMAT, verify=False)


def test_a_newer_format_is_refused(tmp_path):
    original = _write(tmp_path / "a.tst")
    with zipfile.ZipFile(original) as archive:
        manifest = json.loads(archive.read("manifest.json"))
    manifest["format_version"] = 2
    path = _rezip(original, tmp_path / "b.tst", replace={"manifest.json": json.dumps(manifest).encode()})

    error = _refused(path, errors.NEWER_FORMAT, verify=False)

    assert error.params == {"version": 2, "supported": 1}


def test_a_changed_entry_is_refused_by_its_sum(tmp_path):
    path = _rezip(_write(tmp_path / "a.tst"), tmp_path / "b.tst", replace={"texts/0123456789.md": b"other body"})

    error = _refused(path, errors.ENTRY_DAMAGED)

    assert error.params["name"] == "texts/0123456789.md"


def test_an_entry_missing_from_the_archive_is_refused(tmp_path):
    path = _rezip(_write(tmp_path / "a.tst"), tmp_path / "b.tst", drop="texts/0123456789.md")

    error = _refused(path, errors.INVENTORY_MISMATCH)

    assert "texts/0123456789.md" in error.params["missing"]


def test_an_entry_not_in_the_manifest_is_refused(tmp_path):
    path = _rezip(_write(tmp_path / "a.tst"), tmp_path / "b.tst", add={"texts/BBBBBBBBBB.md": b"x"})

    error = _refused(path, errors.INVENTORY_MISMATCH)

    assert "texts/BBBBBBBBBB.md" in error.params["extra"]


def test_a_file_entry_over_the_storage_ceiling_is_refused_while_read(tmp_path):
    path = _write(tmp_path / "a.tst", payload=b"y" * 5000)

    with pytest.raises(TransferError) as caught:
        with _open(path, max_file_bytes=4096) as reader:
            reader.open_manifest()
            reader.verify_inventory()

    assert caught.value.code == errors.ARCHIVE_TOO_LARGE


def test_broken_rows_are_refused(tmp_path):
    original = _write(tmp_path / "a.tst")
    with zipfile.ZipFile(original) as archive:
        manifest = json.loads(archive.read("manifest.json"))
    broken = b"{not json\n"
    for item in manifest["files"]:
        if item["path"] == "rows/items.jsonl":
            item["bytes"] = len(broken)
            item["sha256"] = hashlib.sha256(broken).hexdigest()
    path = _rezip(
        original,
        tmp_path / "b.tst",
        replace={"rows/items.jsonl": broken, "manifest.json": json.dumps(manifest).encode()},
    )

    with pytest.raises(TransferError) as caught:
        with _open(path) as reader:
            reader.open_manifest()
            reader.verify_inventory()
            reader.rows("rows/items.jsonl")

    assert caught.value.code == errors.ENTRY_DAMAGED
