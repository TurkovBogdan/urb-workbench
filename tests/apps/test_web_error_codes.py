"""Каждый код отказа с модулем, который отдаёт бэкенд, переведён на обоих языках интерфейса.

Бэкенд называет понятную ему причину кодом ``<модуль>.<сущность>.<причина>``, а текст даёт
словарь фичи: ``<модуль>.error.<сущность>.<причина>`` (``web/src/api/errorText.ts``). Код без
перевода не ломает показ — человек видит английский запасной текст ответа, — поэтому промах молчит
и ловится здесь. Коды без модуля (``validation_error``, отказы обновления) сюда не входят: у них
английский запасной текст — законный исход.

Код ищется там, где его пишут: константой в ``errors.py`` модуля и аргументом ``code="…"`` у
``ApiError``. Читается текстом, поэтому ``pure``.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

pytestmark = pytest.mark.pure

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
FEATURES = ROOT / "web" / "src" / "features"

_MODULE_CODE = r"[a-z_]+\.[a-z_]+(?:\.[a-z_]+)+"
_CONSTANT = re.compile(rf'^[A-Z_]+ = "({_MODULE_CODE})"', re.M)
_ARGUMENT = re.compile(rf'\bcode="({_MODULE_CODE})"')


def _codes() -> list[str]:
    found = set()
    for path in SRC.rglob("*.py"):
        source = path.read_text(encoding="utf-8")
        if path.name == "errors.py":
            found.update(_CONSTANT.findall(source))
        found.update(_ARGUMENT.findall(source))
    return sorted(found)


def _translation(code: str, locale: str):
    module, *rest = code.split(".")
    path = FEATURES / module / "locales" / f"{locale}.json"
    if not path.exists():
        return None
    node = json.loads(path.read_text(encoding="utf-8")).get("error")
    for step in rest:
        if not isinstance(node, dict):
            return None
        node = node.get(step)
    return node if isinstance(node, str) and node else None


def test_codes_are_found():
    assert "tasks.task.not_found" in _codes()


def test_views_show_errors_through_the_dictionary():
    """Сырой ``e.message`` минует словарь: человек видит английский запасной текст даже тогда,
    когда у причины есть код и перевод. Отказ показывается через ``errorText``."""
    raw = [
        f"{path.relative_to(FEATURES).as_posix()}:{number}"
        for path in FEATURES.rglob("*")
        if path.suffix in (".vue", ".ts") and not {"research", "web_search"} & set(path.parts)
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1)
        if "instanceof Error ? e.message" in line
    ]

    assert not raw, raw


@pytest.mark.parametrize("locale", ["ru", "en"])
@pytest.mark.parametrize("code", _codes())
def test_code_has_its_text(code: str, locale: str):
    assert _translation(code, locale), f"нет перевода {code} в features/{code.split('.')[0]}/locales/{locale}.json"
