"""``notes`` is a level-1 module: it imports no application module, and it is built before them.

The frontend half of the rule is ``BASE_MODULES`` in ``tests/apps/test_web_layer_boundaries.py``;
this is the backend half. Infrastructure modules (``core_*``) are allowed — the change feed is
one — application modules are not, and a single import would turn the dependency upside down.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from src.apps.app.modules import build_modules

pytestmark = pytest.mark.pure

ROOT = Path(__file__).resolve().parents[3] / "src" / "modules" / "notes"
_IMPORT = re.compile(r"^\s*(?:from|import)\s+src\.modules\.(\w+)", re.M)


def _imported_modules() -> dict[str, set[str]]:
    found: dict[str, set[str]] = {}
    for path in sorted(ROOT.rglob("*.py")):
        names = set(_IMPORT.findall(path.read_text(encoding="utf-8")))
        if names:
            found[path.relative_to(ROOT).as_posix()] = names
    return found


def test_the_sweep_reaches_the_module():
    assert {"module.py", "api.py", "crud/note.py"} <= set(_imported_modules())


def test_notes_imports_only_itself_and_infrastructure():
    foreign = {
        path: sorted(name for name in names if name != "notes" and not name.startswith("core_"))
        for path, names in _imported_modules().items()
    }

    assert not {path: names for path, names in foreign.items() if names}


def test_notes_is_built_before_the_modules_that_link_to_it():
    names = [module.name for module in build_modules()]

    assert names.index("notes") < names.index("tasks")
