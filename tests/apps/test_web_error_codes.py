"""Every module-scoped refusal code the backend returns is translated in both interface languages.

The backend names a reason it understands with a code ``<module>.<entity>.<reason>``, and the text
comes from the feature dictionary: ``<module>.error.<entity>.<reason>``
(``web/src/api/errorText.ts``). A code without a translation does not break the display — the
person sees the response's English fallback text — so the miss is silent and is caught here.
Codes without a module (``validation_error``, update refusals) are out of scope: for them the
English fallback text is a legitimate outcome.

A code is looked for where it is written: as a constant in a module's ``errors.py`` and as the
``code="…"`` argument to ``ApiError``. Read as text, hence ``pure``.
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
    """A raw ``e.message`` bypasses the dictionary: the person sees the English fallback text even
    when the reason has a code and a translation. A refusal is shown through ``errorText``."""
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
    assert _translation(code, locale), f"no translation of {code} in features/{code.split('.')[0]}/locales/{locale}.json"
