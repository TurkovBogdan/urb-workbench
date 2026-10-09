"""The ENV form is labelled from the dictionary in both languages.

The backend serves field labels as English fallback text (``core_setup/keys.py``), and the form
looks the translation up by group code and the field's ENV key
(``web/src/features/setup/labels.ts``). A field added on the backend without a dictionary string
does not break the page — it just comes out in English in the Russian interface. Here it fails
at once.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.modules.core_setup.keys import FIELDS, GROUP_LABELS

pytestmark = pytest.mark.pure

LOCALES = Path(__file__).resolve().parents[2] / "web" / "src" / "features" / "setup" / "locales"


def _strings(locale: str) -> dict:
    return json.loads((LOCALES / f"{locale}.json").read_text(encoding="utf-8"))


@pytest.mark.parametrize("locale", ["ru", "en"])
def test_every_group_has_its_title(locale: str):
    groups = _strings(locale)["group"]

    assert sorted(code for code in GROUP_LABELS if not groups.get(code)) == []


@pytest.mark.parametrize("locale", ["ru", "en"])
def test_every_field_has_its_label_and_description(locale: str):
    fields = _strings(locale)["field"]

    missing = [
        f"{field.key}.{part}"
        for field in FIELDS
        for part in ("label", "description")
        if (part == "label" or field.description) and not fields.get(field.key, {}).get(part)
    ]

    assert missing == []


def test_every_field_belongs_to_a_known_group():
    assert {field.group for field in FIELDS} <= set(GROUP_LABELS)
