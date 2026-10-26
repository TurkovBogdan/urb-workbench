"""The header rules on their own: which types are sandboxed, how a name is written, when a tag matches."""

from __future__ import annotations

import pytest

from src.modules.core_storage_view.headers import content_disposition, etag_matches, is_sandboxed

pytestmark = pytest.mark.pure


@pytest.mark.parametrize(
    "mime",
    [
        "text/html",
        "text/html; charset=utf-8",
        "application/xhtml+xml",
        "application/xml",
        "text/xml",
        "image/svg+xml",
        "IMAGE/SVG+XML",
        "application/rss+xml",
    ],
)
def test_a_type_that_can_run_script_is_sandboxed(mime):
    assert is_sandboxed(mime)


@pytest.mark.parametrize(
    "mime", ["image/png", "application/pdf", "text/plain", "text/markdown", "application/octet-stream"]
)
def test_a_passive_type_is_not_sandboxed(mime):
    assert not is_sandboxed(mime)


def test_a_plain_ascii_name_is_its_own_fallback():
    assert content_disposition("report v2.pdf", "C.pdf", download=False) == (
        "inline; filename=\"report v2.pdf\"; filename*=UTF-8''report%20v2.pdf"
    )


@pytest.mark.parametrize("name", ['say "hi".txt', "back\\slash.txt", "100%.txt", "имя.txt", "tab\there.txt"])
def test_a_name_unsafe_in_quotes_falls_back_to_the_code(name):
    header = content_disposition(name, "ABCDEF0123.txt", download=True)

    assert header.startswith('attachment; filename="ABCDEF0123.txt"; filename*=UTF-8\'\'')
    assert header.isascii()
    assert '"' not in header.split("filename*=", 1)[1]


@pytest.mark.parametrize(
    ("header", "matches"),
    [
        ('"abc"', True),
        ('W/"abc"', True),
        ('"x", "abc"', True),
        ("*", True),
        ('"abd"', False),
        ("", False),
        (None, False),
    ],
)
def test_if_none_match(header, matches):
    assert etag_matches(header, '"abc"') is matches
