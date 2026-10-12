"""``codex`` stands on ``workspace`` alone and carries no agent surface.

The level test (``tests/apps/test_python_layer_boundaries.py``) would let a level-2 module import
any level-1 one; the codex is narrower on purpose — it does not use ``notes``, and an import from
there would be the first step to a codex note that is a ``notes`` document after all.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from src.apps.app.modules import build_modules

pytestmark = pytest.mark.pure

ROOT = Path(__file__).resolve().parents[3] / "src" / "modules" / "codex"
_IMPORT = re.compile(r"^\s*(?:from|import)\s+src\.modules\.(\w+)", re.M)


def _imported_modules() -> dict[str, set[str]]:
    found: dict[str, set[str]] = {}
    for path in sorted(ROOT.rglob("*.py")):
        names = set(_IMPORT.findall(path.read_text(encoding="utf-8")))
        if names:
            found[path.relative_to(ROOT).as_posix()] = names
    return found


def test_the_sweep_reaches_the_module():
    imported = _imported_modules()
    assert {"module.py", "models/mount.py", "crud/code.py"} <= set(imported)
    assert "workspace" in imported["models/mount.py"]


def test_codex_imports_only_itself_workspace_and_infrastructure():
    allowed = {"codex", "workspace"}
    foreign = {
        path: sorted(n for n in names if n not in allowed and not n.startswith("core_"))
        for path, names in _imported_modules().items()
    }

    assert not {path: names for path, names in foreign.items() if names}


def test_codex_is_built_after_workspace_and_before_the_agent_surface():
    names = [module.name for module in build_modules()]

    assert names.index("workspace") < names.index("codex") < names.index("workbench")
