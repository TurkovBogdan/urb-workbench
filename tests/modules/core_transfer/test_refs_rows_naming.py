"""References rewritten in one pass, rows translated by the model's columns, the file name."""

from __future__ import annotations

from datetime import datetime

import pytest

from src.modules.core_storage.models import CoreStorageFile
from src.modules.core_transfer import errors
from src.modules.core_transfer.errors import TransferError
from src.modules.core_transfer.naming import archive_file_name
from src.modules.core_transfer.refs import ReferenceScheme
from src.modules.core_transfer.rows import clip_to_columns, json_to_values, row_to_json

pytestmark = pytest.mark.pure

SCHEME = ReferenceScheme(["TASK", "NOTE", "FILE"], aliases={"IMAGE": "FILE"})


def test_a_rewrite_never_chains():
    text = "see TASK@AAAAAAAAAA and TASK@BBBBBBBBBB"
    mapping = {("TASK", "AAAAAAAAAA"): "BBBBBBBBBB", ("TASK", "BBBBBBBBBB"): "CCCCCCCCCC"}

    rewritten, count = SCHEME.rewrite(text, mapping)

    assert rewritten == "see TASK@BBBBBBBBBB and TASK@CCCCCCCCCC"
    assert count == 2


def test_the_type_is_part_of_the_key():
    text = "NOTE@AAAAAAAAAA TASK@AAAAAAAAAA"

    rewritten, _ = SCHEME.rewrite(text, {("NOTE", "AAAAAAAAAA"): "1111111111"})

    assert rewritten == "NOTE@1111111111 TASK@AAAAAAAAAA"


def test_a_picture_follows_its_file_and_keeps_its_word():
    text = "![x](IMAGE@AAAAAAAAAA) and FILE@AAAAAAAAAA"

    rewritten, count = SCHEME.rewrite(text, {("FILE", "AAAAAAAAAA"): "2222222222"})

    assert rewritten == "![x](IMAGE@2222222222) and FILE@2222222222"
    assert count == 2


def test_a_lower_case_code_is_found_and_written_upper():
    rewritten, _ = SCHEME.rewrite("task@aaaaaaaaaa", {("TASK", "AAAAAAAAAA"): "3333333333"})

    assert rewritten == "task@3333333333"
    assert SCHEME.collect("Note@bbbbbbbbbb") == {("NOTE", "BBBBBBBBBB")}


def test_a_longer_hash_is_not_a_reference():
    text = "TASK@AAAAAAAAAAAAAAAAAAAAAA"

    assert SCHEME.collect(text) == set()
    assert SCHEME.rewrite(text, {("TASK", "AAAAAAAAAA"): "4444444444"}) == (text, 0)


def test_a_longer_word_wins_over_its_prefix():
    scheme = ReferenceScheme(["TASK", "TASKGROUP"])

    assert scheme.collect("TASKGROUP@AAAAAAAAAA") == {("TASKGROUP", "AAAAAAAAAA")}


def test_a_row_round_trips_by_its_columns():
    row = CoreStorageFile(
        code="AAAAAAAAAA", store="public", sha256="0" * 64, type="image", size=12,
        mime="image/png", extension=".png", created_at=datetime(2026, 10, 26, 7, 8, 9),
    )

    data = row_to_json(row)
    back = json_to_values(CoreStorageFile, {**data, "unknown": "ignored"})

    assert data["created_at"] == "2026-10-26 07:08:09"
    assert back["created_at"] == datetime(2026, 10, 26, 7, 8, 9)
    assert back["deleted_at"] is None
    assert "unknown" not in back


def test_a_missing_column_takes_its_default_or_refuses():
    values = json_to_values(CoreStorageFile, {
        "code": "AAAAAAAAAA", "store": "public", "sha256": "0" * 64, "type": "image", "size": 1,
        "mime": "image/png", "extension": ".png",
    })
    assert isinstance(values["created_at"], datetime)

    with pytest.raises(TransferError) as caught:
        json_to_values(CoreStorageFile, {"code": "AAAAAAAAAA"})
    assert caught.value.code == errors.ARCHIVE_INCONSISTENT


def test_a_malformed_timestamp_refuses():
    with pytest.raises(TransferError) as caught:
        json_to_values(CoreStorageFile, {
            "code": "A", "store": "p", "sha256": "0", "type": "t", "size": 1, "mime": "m",
            "extension": "", "created_at": "yesterday",
        })
    assert caught.value.code == errors.ARCHIVE_INCONSISTENT


_FILE_ROW = {
    "code": "AAAAAAAAAA", "store": "public", "sha256": "0" * 64, "type": "image", "size": 1,
    "mime": "image/png", "extension": ".png", "created_at": "2026-10-26 07:08:09",
}


@pytest.mark.parametrize(("field", "value"), [
    ("size", "12"), ("size", True), ("size", 1.5), ("mime", 5), ("mime", {"a": 1}), ("store", None),
])
def test_a_value_that_does_not_fit_its_column_refuses(field, value):
    with pytest.raises(TransferError) as caught:
        json_to_values(CoreStorageFile, {**_FILE_ROW, field: value})

    assert caught.value.code == errors.ARCHIVE_INCONSISTENT
    assert caught.value.params["detail"] == f"core_storage_file.{field}"


def test_zero_and_an_empty_string_are_values():
    values = json_to_values(CoreStorageFile, {**_FILE_ROW, "size": 0, "extension": ""})

    assert (values["size"], values["extension"]) == (0, "")
    assert json_to_values(CoreStorageFile, {**_FILE_ROW, "deleted_at": None})["deleted_at"] is None


def test_values_are_cut_to_their_columns():
    values, clipped = clip_to_columns(CoreStorageFile, {"store": "x" * 40, "mime": "ok"})

    assert len(values["store"]) == 32
    assert clipped == ["store"]


@pytest.mark.parametrize(
    ("title", "expected"),
    [
        ("План: релиз 1/2?", "План- релиз 1-2-.utsk"),
        ("Точка в конце.", "Точка в конце.utsk"),
        ("   ", "task-ABC.utsk"),
        ('<>:"/\\|?*', "task-ABC.utsk"),
        ("строка\nвторая", "строка вторая.utsk"),
    ],
)
def test_the_file_name_is_the_cleaned_title(title, expected):
    assert archive_file_name(title, fallback="task-ABC", extension=".utsk") == expected


def test_a_long_title_is_cut_by_characters():
    name = archive_file_name("я" * 200, fallback="x", extension=".utsk")

    assert name == "я" * 80 + ".utsk"
