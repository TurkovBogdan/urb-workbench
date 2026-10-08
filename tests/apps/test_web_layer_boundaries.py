"""Dependency direction in the SPA: the foundation knows nothing of modules, nor modules of each
other.

``web/src`` splits into two tiers with OPPOSITE directions of coupling. The **foundation**
(``api``, ``shared``, ``components``, ``composables``, ``constants``, ``stores``, ``layout``) is
what modules import; it knows nothing of them itself. **Composition** (``router``, ``plugins``,
``views``) is the reverse — it assembles the modules together. A layer that lands in both lists
is a cycle: editing a module would drag along the shell that loads that very module.

Hence the rule for a shared component: a component with one consumer lives inside its module,
and moving it into the foundation is allowed from the second consumer on — and only together
with dropping the domain type.

**The exception is base modules** (``BASE_MODULES``). These are level-1 modules: they hold an
entity the application modules rest on, and themselves know none of them. Today there are two.
``workspace``: the workspace narrows the data of every module above it, and routing its context
through the foundation would be a lie — the foundation knows nothing of the domain, and this is
the domain itself. ``notes``: a document is the same entity wherever a module above uses it. So the rule is not "nobody depends on anybody" but "dependencies go down the
levels and only down": a base reaching into an application module is an error of the same cost
as before, and is caught right here.

Composition is deliberately left unchecked, and that is not an oversight: ``plugins/i18n.ts``
finds module dictionaries by glob, and the design-system showcase (``views/design-system``) still
reaches into ``research`` — a separate piece of work, already split out on its own.

The check lives in the Python tests for the same reason as the page frame (see
``test_web_page_header.py``): the frontend has no test runner, and the convention has to be
checkable. Sources are read as text — no build, no browser, hence ``pure``.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

pytestmark = pytest.mark.pure

WEB_SRC = Path(__file__).resolve().parents[2] / "web" / "src"

FOUNDATION = ("api", "shared", "components", "composables", "constants", "stores", "layout")
MODULES_ROOT = WEB_SRC / "features"

# Level-1 modules are bases: an application module may refer to them, they may not refer to it.
# Mirrors the backend, where ``workspace`` and ``notes`` precede in the module list those holding
# an FK to them.
BASE_MODULES = ("workspace", "notes")

SOURCE_SUFFIXES = (".ts", ".vue")

# A static `from '…'`, a side-effect `import '…'` and a lazy `import('…')` — all three forms carry
# a dependency, and the rule would leak past any one of them.
SPECIFIER = re.compile(r"""(?:from|import)\s*\(?\s*['"]([^'"]+)['"]""")


def _sources(root: Path) -> list[tuple[str, str]]:
    found = []
    for path in sorted(root.rglob("*")):
        if path.suffix in SOURCE_SUFFIXES:
            found.append((path.relative_to(WEB_SRC).as_posix(), path.read_text(encoding="utf-8")))
    return found


def _foundation_sources() -> list[tuple[str, str]]:
    return [source for layer in FOUNDATION for source in _sources(WEB_SRC / layer)]


def _module_sources() -> list[tuple[str, str]]:
    return _sources(MODULES_ROOT)


def _imported_paths(name: str, source: str) -> list[str]:
    """Where a file's imports point, in ``web/src`` coordinates.

    An alias and a relative path count the same: otherwise `../../<another module>` would bypass
    the rule silently, leaving the test green over a live violation. A package name (neither `@/`
    nor a dot) is not our concern.
    """
    here = (WEB_SRC / name).parent
    inside_web_src = []
    for specifier in SPECIFIER.findall(source):
        if specifier.startswith("@/"):
            target = WEB_SRC / specifier[2:]
        elif specifier.startswith("."):
            target = (here / specifier).resolve()
        else:
            continue
        if target.is_relative_to(WEB_SRC):
            inside_web_src.append(target.relative_to(WEB_SRC).as_posix())
    return inside_web_src


def _module_of(path: str) -> str | None:
    parts = path.split("/")
    return parts[1] if parts[0] == "features" and len(parts) > 1 else None


def _case_id(value: str) -> str:
    """The case name is the file path; the pair's second element is its source, which is no good
    as a name: the multi-line text would end up whole in every node id."""
    return "" if "\n" in value else value


def test_both_tiers_are_actually_walked():
    """A silently green test is worse than none: if a directory moves, we fail here."""
    assert len(_foundation_sources()) > 80
    assert len(_module_sources()) > 60


@pytest.mark.parametrize(
    "name,source",
    _foundation_sources(),
    ids=_case_id,
)
def test_foundation_does_not_import_a_module(name: str, source: str):
    for imported in _imported_paths(name, source):
        assert _module_of(imported) is None, (
            f"{name}: the foundation reaches into a module ({imported}) — the shell can no longer be built without it"
        )


@pytest.mark.parametrize(
    "name,source",
    _module_sources(),
    ids=_case_id,
)
def test_a_module_does_not_import_another_module(name: str, source: str):
    """References may go down the levels: to the foundation and to a base module, nowhere else."""
    own = _module_of(name)
    allowed = (None, own, *(() if own in BASE_MODULES else BASE_MODULES))
    for imported in _imported_paths(name, source):
        other = _module_of(imported)
        assert other in allowed, (
            f"{name}: a module reaches into a module ({imported}) — what they share belongs in the foundation"
            if other not in BASE_MODULES
            else f"{name}: a base reaches into an application module ({imported}) — an upward dependency"
        )
