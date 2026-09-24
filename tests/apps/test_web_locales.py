"""Английский словарь повторяет русский ключ в ключ.

Русский — язык авторства, английский — язык по умолчанию (`web/src/constants/language.ts`).
Ключ, забытый в `en.json`, не роняет страницу: `vue-i18n` молча падает на русский
(`fallbackLocale`), и в английском интерфейсе появляется русская строка, которую замечают
глазами — если замечают. Здесь это падает сразу, как и расхождение в подстановках: `{count}`,
потерянный при переводе, рисуется пустым местом.

Неподключённые к оболочке фичи (`research`, `web_search`) идут под удаление и полного английского
словаря не получают. У `research` он частичный — ровно те ключи, которые просят её компоненты,
показанные в витрине дизайн-системы; остальное падает на русский.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

pytestmark = pytest.mark.pure

WEB_SRC = Path(__file__).resolve().parents[2] / "web" / "src"
FEATURES = WEB_SRC / "features"

UNWIRED_FEATURES = ("research", "web_search")

_PLACEHOLDER = re.compile(r"\{(\w+)\}")
_CYRILLIC = re.compile(r"[А-Яа-яЁё]")


def _dictionaries() -> list[Path]:
    roots = [WEB_SRC / "locales", WEB_SRC / "locales" / "design-system"]
    roots += [
        path / "locales"
        for path in sorted(FEATURES.iterdir())
        if (path / "locales" / "ru.json").exists() and path.name not in UNWIRED_FEATURES
    ]
    return roots


def _leaves(node, prefix: str = ""):
    if isinstance(node, dict):
        for key, value in node.items():
            yield from _leaves(value, f"{prefix}.{key}" if prefix else key)
    elif isinstance(node, list):
        for index, value in enumerate(node):
            yield from _leaves(value, f"{prefix}[{index}]")
    else:
        yield prefix, node


def _load(path: Path) -> dict[str, str]:
    return dict(_leaves(json.loads(path.read_text(encoding="utf-8"))))


def _id(root: Path) -> str:
    return root.relative_to(WEB_SRC).parent.as_posix()


@pytest.mark.parametrize("root", _dictionaries(), ids=_id)
def test_english_has_exactly_the_russian_keys(root: Path):
    russian = _load(root / "ru.json")
    english = _load(root / "en.json")

    assert list(english) == list(russian)


@pytest.mark.parametrize("root", _dictionaries(), ids=_id)
def test_english_keeps_every_placeholder(root: Path):
    russian = _load(root / "ru.json")
    english = _load(root / "en.json")

    lost = {
        key: (sorted(_PLACEHOLDER.findall(str(value))), sorted(_PLACEHOLDER.findall(str(english.get(key)))))
        for key, value in russian.items()
        if set(_PLACEHOLDER.findall(str(value))) != set(_PLACEHOLDER.findall(str(english.get(key))))
    }

    assert not lost, lost


@pytest.mark.parametrize("root", _dictionaries(), ids=_id)
def test_english_carries_no_russian_text(root: Path):
    english = _load(root / "en.json")

    assert not {key: value for key, value in english.items() if _CYRILLIC.search(str(value))}
