"""Module levels on the backend: a module imports only what lies strictly below it.

The application's modules are stacked, and the stack is what lets one be removed or added without
touching its neighbours:

- level 1 — ``workspace``, ``notes``: the base entities, importing no application module;
- level 2 — ``tasks``: a domain on top of them;
- level 3 — ``workbench``: the agent surface, built on every domain below it.

A module of level N may import modules of levels below N only — not its own level, not above.
The platform (``src/core`` and every ``core_*`` module) sits under all of them and imports none.
Every ``src/modules`` package must be one or the other: a new module that is not given a level
here fails the census below, rather than slipping past the check unclassified.

The domain modules also carry no agent-surface code: no ``mcp/`` package and no ``fastmcp``
import — that is all ``workbench``'s.

Imports are read with ``ast`` from every ``.py`` file, function bodies and ``TYPE_CHECKING``
blocks included: a deferred import is still a dependency, only a later one. The frontend's own
boundaries are ``test_web_layer_boundaries.py``.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

pytestmark = pytest.mark.pure

_SRC = Path(__file__).resolve().parents[2] / "src"
_MODULES = _SRC / "modules"
_PLATFORM_PREFIX = "core_"

LEVELS = {
    "workspace": 1,
    "notes": 1,
    "tasks": 2,
    "workbench": 3,
}

# What only the agent surface may hold.
_AGENT_SURFACE_IMPORTS = ("fastmcp",)


def _imported(path: Path) -> set[str]:
    """Every absolute module name a file imports, wherever in the file the import sits."""
    names: set[str] = set()
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"), filename=str(path))):
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            names.add(node.module)
            names.update(f"{node.module}.{alias.name}" for alias in node.names)
    return names


def _module_of(name: str) -> str | None:
    """``src.modules.tasks.crud.task`` → ``tasks``; anything outside ``src.modules`` → ``None``."""
    parts = name.split(".")
    if parts[:2] == ["src", "modules"] and len(parts) > 2:
        return parts[2]
    return None


def _python_files(root: Path) -> list[Path]:
    return sorted(path for path in root.rglob("*.py") if "__pycache__" not in path.parts)


def level_violations(modules_root: Path, levels: dict[str, int]) -> list[str]:
    """``file → module`` imports that point at the importer's own level or above.

    A leveled module importing a platform module is fine; a platform module importing a leveled
    one is not — the platform sits under every level.
    """
    found = []
    for package in sorted(p for p in modules_root.iterdir() if (p / "__init__.py").is_file()):
        own = package.name
        own_level = levels.get(own, 0)
        for path in _python_files(package):
            for target in sorted({_module_of(name) for name in _imported(path)} - {None, own}):
                target_level = levels.get(target, 0)
                if target_level and target_level >= own_level:
                    found.append(
                        f"{path.relative_to(modules_root)} (level {own_level}) imports "
                        f"{target} (level {target_level})"
                    )
    return found


def _packages() -> list[str]:
    return sorted(p.name for p in _MODULES.iterdir() if (p / "__init__.py").is_file())


# ── the real tree ─────────────────────────────────────────────────────────────


def test_every_module_is_either_platform_or_has_a_level():
    unclassified = [
        name
        for name in _packages()
        if not name.startswith(_PLATFORM_PREFIX) and name not in LEVELS
    ]

    assert unclassified == [], f"give these a level in LEVELS: {unclassified}"


def test_no_module_imports_its_own_level_or_above():
    assert level_violations(_MODULES, LEVELS) == []


def test_the_core_imports_no_application_module():
    offenders = [
        f"{path.relative_to(_SRC)} imports {target}"
        for path in _python_files(_SRC / "core")
        for target in sorted({_module_of(name) for name in _imported(path)} - {None})
        if target in LEVELS
    ]

    assert offenders == []


@pytest.mark.parametrize("module", [name for name, level in LEVELS.items() if level < 3])
def test_a_domain_module_holds_no_agent_surface(module):
    package = _MODULES / module
    offenders = [
        f"{path.relative_to(_MODULES)} imports {name}"
        for path in _python_files(package)
        for name in sorted(_imported(path))
        if name.split(".")[0] in _AGENT_SURFACE_IMPORTS
    ]

    assert not (package / "mcp").exists()
    assert offenders == []


# ── the check itself can go red ───────────────────────────────────────────────


def _tree(root: Path, files: dict[str, str]) -> Path:
    for relative, text in files.items():
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    return root


@pytest.mark.parametrize(
    ("importer", "line"),
    [
        ("tasks", "from src.modules.workbench.server import mcp_server"),
        ("notes", "import src.modules.workspace.crud"),
        ("workspace", "    from src.modules.tasks import models  # deferred, still a dependency"),
        ("core_changes", "from src.modules.notes.models import Note"),
    ],
)
def test_an_import_at_the_same_level_or_above_is_caught(tmp_path, importer, line):
    body = f"def late():\n{line}\n" if line.startswith(" ") else f"{line}\n"
    root = _tree(
        tmp_path,
        {
            "workspace/__init__.py": "",
            "notes/__init__.py": "",
            "tasks/__init__.py": "",
            "workbench/__init__.py": "",
            "core_changes/__init__.py": "",
            f"{importer}/offender.py": body,
        },
    )

    assert len(level_violations(root, LEVELS)) == 1


def test_an_import_from_below_or_from_the_platform_passes(tmp_path):
    root = _tree(
        tmp_path,
        {
            "workspace/__init__.py": "from src.modules.core_changes import bus\n",
            "tasks/__init__.py": "from src.modules.workspace.crud import workspace\n",
            "workbench/__init__.py": (
                "from src.modules.tasks.crud import task\nfrom src.modules.notes import rules\n"
            ),
            "core_changes/__init__.py": "",
        },
    )

    assert level_violations(root, LEVELS) == []
