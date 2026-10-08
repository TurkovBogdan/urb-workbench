"""The task form's length caps mirror the database columns they guard.

``web/src/features/tasks/labels.ts`` repeats the caps of ``tasks/constants.py`` so that a field
stops the typing instead of the backend refusing after submit. A cap raised on one side only
fails silently: a lower one on the page cuts text the column would hold, a higher one lets the
person type what the save then refuses.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from src.modules.tasks import constants

pytestmark = pytest.mark.pure

LABELS = Path(__file__).resolve().parents[2] / "web" / "src" / "features" / "tasks" / "labels.ts"

# Each page constant and the backend constant it mirrors.
MIRRORS = {
    "TASK_TITLE_MAX": "TITLE_MAX",
    "TASK_DESCRIPTION_MAX": "DESCRIPTION_MAX",
    "GROUP_DESCRIPTION_MAX": "GROUP_DESCRIPTION_MAX",
    "TASK_CONTEXT_MAX": "CONTEXT_MAX",
    "TASK_CONSTRAINTS_MAX": "CONSTRAINTS_MAX",
    "TASK_CRITERIA_MAX": "CRITERIA_MAX",
    "TASK_PLAN_MAX": "PLAN_MAX",
    "TASK_PROGRESS_MAX": "PROGRESS_MAX",
    "TASK_RESULT_MAX": "RESULT_MAX",
    "BODY_MAX": "BODY_MAX",
    "STAGE_EVIDENCE_MAX": "EVIDENCE_MAX",
    "NOTE_BODY_MAX": "NOTE_BODY_MAX",
    "NOTE_RESOLUTION_MAX": "RESOLUTION_MAX",
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
