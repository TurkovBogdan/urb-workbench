"""Форма ENV подписана словарём на обоих языках.

Бэкенд отдаёт подписи полей английским запасным текстом (``core_setup/keys.py``), а форма берёт
перевод по коду группы и ENV-ключу поля (``web/src/features/setup/labels.ts``). Поле, добавленное
на бэке без строки в словаре, не ломает страницу — оно просто выходит английским в русском
интерфейсе. Здесь это падает сразу.
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
