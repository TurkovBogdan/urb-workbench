"""A note's length caps on the page mirror the ``notes`` columns they guard.

``web/src/features/notes/labels.ts`` repeats the caps of ``notes/constants.py`` so that a field
stops the typing instead of the backend refusing after the save. A cap raised on one side only
fails silently: lower on the page cuts what the column holds, higher lets the person type what the
save then refuses.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from src.modules.notes import constants

pytestmark = pytest.mark.pure

LABELS = Path(__file__).resolve().parents[2] / "web" / "src" / "features" / "notes" / "labels.ts"

MIRRORS = {
    "NOTE_TITLE_MAX": "TITLE_MAX",
    "NOTE_DESCRIPTION_MAX": "DESCRIPTION_MAX",
    "NOTE_BODY_MAX": "BODY_MAX",
}


def _page_caps() -> dict[str, int]:
    source = LABELS.read_text(encoding="utf-8")
    return {
        name: int(value)
        for name, value in re.findall(r"^export const (\w+_MAX) = (\d+)$", source, re.MULTILINE)
    }


def test_every_page_cap_is_mirrored_and_none_is_left_out():
    assert set(_page_caps()) == set(MIRRORS)


@pytest.mark.parametrize(("page", "backend"), sorted(MIRRORS.items()))
def test_a_page_cap_equals_its_column(page: str, backend: str):
    assert _page_caps()[page] == getattr(constants, backend)
