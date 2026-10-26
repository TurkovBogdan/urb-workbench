"""How an original name splits into ``original_filename`` + ``original_extension``.

The two put together must give the name back exactly as it came in.
"""

from __future__ import annotations

import pytest

from src.modules.core_storage.constants import EXTENSION_MAX, ORIGINAL_FILENAME_MAX
from src.modules.core_storage.names import OriginalName, split_filename

pytestmark = pytest.mark.pure

LONGEST_SUFFIX = "." + "x" * (EXTENSION_MAX - 1)
TOO_LONG_SUFFIX = "." + "x" * EXTENSION_MAX


@pytest.mark.parametrize(
    ("brought", "filename", "extension"),
    [
        ("report.final.PDF", "report.final", ".PDF"),
        ("archive.tar.gz", "archive.tar", ".gz"),
        ("отчёт.ДОКХ", "отчёт", ".ДОКХ"),
        ("README", "README", ""),
        (".env", ".env", ""),
        ("report.", "report.", ""),
        ("", "", ""),
        (f"x{LONGEST_SUFFIX}", "x", LONGEST_SUFFIX),
        (f"x{TOO_LONG_SUFFIX}", f"x{TOO_LONG_SUFFIX}", ""),
        ("x.pdf/", "x.pdf/", ""),
    ],
    ids=[
        "upper-case-suffix",
        "last-suffix-only",
        "cyrillic",
        "no-suffix",
        "dotfile",
        "trailing-dot",
        "empty",
        "suffix-at-the-width",
        "suffix-over-the-width",
        "suffix-not-at-the-end",
    ],
)
def test_a_name_splits_before_its_last_suffix_and_comes_back_whole(brought, filename, extension):
    name = split_filename(brought)
    assert name == OriginalName(filename=filename, extension=extension)
    assert name.filename + name.extension == brought


def test_the_width_counts_the_name_without_its_extension():
    at_width = "n" * ORIGINAL_FILENAME_MAX
    assert split_filename(f"{at_width}.pdf") == OriginalName(at_width, ".pdf")
    with pytest.raises(ValueError):
        split_filename(f"n{at_width}.pdf")


def test_a_suffix_too_wide_for_its_column_counts_towards_the_name():
    with pytest.raises(ValueError):
        split_filename("n" * (ORIGINAL_FILENAME_MAX - len(TOO_LONG_SUFFIX) + 1) + TOO_LONG_SUFFIX)


@pytest.mark.parametrize("brought", [None, b"report.pdf", 7])
def test_a_name_that_is_not_a_string_is_refused(brought):
    with pytest.raises(ValueError):
        split_filename(brought)


@pytest.mark.parametrize(
    "brought",
    ["x\x00.png", "shot\x01\nname.png", "line\r.txt", "tab\tbed.txt", "del\x7f.txt", "x.pn\x1fg"],
    ids=["nul", "soh-and-newline", "carriage-return", "tab", "del", "in-the-suffix"],
)
def test_a_name_with_a_control_character_is_refused(brought):
    """A name is one line — read in a list, a ``Content-Disposition`` header, an answer to the
    agent — and PostgreSQL cannot store U+0000 at all."""
    with pytest.raises(ValueError, match="control character"):
        split_filename(brought)


@pytest.mark.parametrize("brought", ["Отчёт за май.pdf", "a b.txt", "x y.png", "名前.png"])
def test_a_name_with_printable_characters_only_is_kept(brought):
    name = split_filename(brought)
    assert name.filename + name.extension == brought
