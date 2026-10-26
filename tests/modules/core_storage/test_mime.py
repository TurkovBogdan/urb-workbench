"""What a file is: the signature first, the name's extension for formats without one."""

from __future__ import annotations

import io
import zipfile

import pytest

from src.modules.core_storage.mime import detect

pytestmark = pytest.mark.pure

PNG = bytes.fromhex("89504e470d0a1a0a0000000d49484452") + b"\x00" * 32
JPEG = bytes.fromhex("ffd8ffe000104a464946") + b"\x00" * 32


def _zip() -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("a.txt", "a")
    return buffer.getvalue()


def test_the_signature_wins_over_a_lying_name():
    detected = detect(PNG, "notes.md")
    assert (detected.mime, detected.extension, detected.type) == ("image/png", ".png", "image")


def test_jpeg_is_stored_as_jpg():
    assert detect(JPEG, "photo.jpeg").extension == ".jpg"


@pytest.mark.parametrize(
    "name, mime, extension",
    [
        ("plan.md", "text/markdown", ".md"),
        ("PLAN.MD", "text/markdown", ".md"),
        ("run.log", "text/plain", ".txt"),
        ("data.csv", "text/csv", ".csv"),
        ("config.yml", "application/yaml", ".yaml"),
        ("dump.json", "application/json", ".json"),
    ],
)
def test_text_formats_go_by_the_extension(name, mime, extension):
    detected = detect(b"plain text without a signature", name)
    assert (detected.mime, detected.extension) == (mime, extension)


def test_csv_is_a_table():
    assert detect(b"a,b\n1,2\n", "data.csv").type == "table"


def test_an_archive_is_recognised_by_its_bytes():
    detected = detect(_zip(), "")
    assert (detected.mime, detected.type) == ("application/zip", "archive")


def test_an_unknown_file_is_octet_stream_of_type_other():
    detected = detect(b"\x01\x02\x03 no signature", "blob.unknownext")
    assert (detected.mime, detected.extension, detected.type) == (
        "application/octet-stream",
        "",
        "other",
    )


def test_an_empty_file_without_a_name_is_unknown():
    assert detect(b"", "").mime == "application/octet-stream"
