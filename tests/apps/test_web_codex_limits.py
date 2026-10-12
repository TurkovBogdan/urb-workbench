"""The codex page's caps and segment rule mirror the ``codex`` module they guard.

``web/src/features/codex/labels.ts`` repeats the caps of ``codex/constants.py``, the depth limit and
the segment pattern of ``codex/rules.py``, so that a field stops the typing and the save button
stays off instead of the backend refusing after the save. A rule changed on one side only fails
silently: the page then offers a segment the backend refuses, or refuses one it would take.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from src.modules.codex import constants, rules

pytestmark = pytest.mark.pure

LABELS = Path(__file__).resolve().parents[2] / "web" / "src" / "features" / "codex" / "labels.ts"

MIRRORS = {
    "CODEX_SEGMENT_MAX": constants.SEGMENT_MAX,
    "CODEX_TITLE_MAX": constants.TITLE_MAX,
    "CODEX_DESCRIPTION_MAX": constants.DESCRIPTION_MAX,
    "CODEX_BODY_MAX": constants.BODY_MAX,
    "CODEX_DEPTH_MAX": rules.DEPTH_MAX,
}
# The navigation panel's width is the page's own; no column stands behind it.
PAGE_ONLY = {"CODEX_NAV_WIDTH_MAX"}


def _source() -> str:
    return LABELS.read_text(encoding="utf-8")


def _page_caps() -> dict[str, int]:
    return {
        name: int(value)
        for name, value in re.findall(r"^export const (\w+_MAX) = (\d+)$", _source(), re.MULTILINE)
    }


def test_every_page_cap_is_mirrored_and_none_is_left_out():
    assert set(_page_caps()) == set(MIRRORS) | PAGE_ONLY


@pytest.mark.parametrize(("page", "backend"), sorted(MIRRORS.items()))
def test_a_page_cap_equals_the_backend(page: str, backend: int):
    assert _page_caps()[page] == backend


def test_the_page_segment_pattern_is_the_backend_rule():
    [page] = re.findall(
        r"^export const CODEX_SEGMENT_PATTERN = /\^(.+)\$/$", _source(), re.MULTILINE
    )

    assert page == rules.SEGMENT_PATTERN.pattern
