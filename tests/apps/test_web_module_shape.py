"""The shape of a frontend module folder: every folder under ``web/src/features/`` is laid out
the same way.

The convention grew on its own — the module entry (``api.ts`` + ``routes.ts`` + ``views/``), its
own string dictionary (``locales/ru.json``, which is also the module namespace in
``plugins/i18n.ts``), composables in ``composables/``, and a single name for the file that turns
backend codes into labels (``labels.ts``). As long as it is written down nowhere, the next folder
is set up by eye, and the divergence is noticed only when the module moves.

The check lives in the Python tests rather than the frontend, for the same reason as the page
frame standard (``test_web_page_header.py``): the frontend has no test runner, and the convention
has to be checkable. We read the file tree — no build or browser needed, hence ``pure``. It sits
in ``apps``: the rule is about the application as a whole, not a single module, and this way it
lands in the regular ``--core`` run.
"""

from __future__ import annotations

from pathlib import Path

import pytest

pytestmark = pytest.mark.pure

WEB_SRC = Path(__file__).resolve().parents[2] / "web" / "src"
FEATURES = WEB_SRC / "features"

ENTRY_POINTS = ("api.ts", "routes.ts", "views")

# A module dictionary is wired by folder name (`import.meta.glob` in `plugins/i18n.ts`), so a
# folder without one is not merely "untranslated" — its strings have nowhere to go at all.
DICTIONARY = "locales/ru.json"


def _modules() -> list[str]:
    return sorted(path.name for path in FEATURES.iterdir() if path.is_dir())


def test_modules_are_found():
    """The walk itself: if folders stop being found, a silently green test is worse than none."""
    assert len(_modules()) > 5


@pytest.mark.parametrize("module", _modules(), ids=lambda value: value)
def test_module_has_its_entry_points(module: str):
    for entry in ENTRY_POINTS:
        assert (FEATURES / module / entry).exists(), f"{module}: no {entry}"


@pytest.mark.parametrize("module", _modules(), ids=lambda value: value)
def test_module_has_its_dictionary(module: str):
    assert (FEATURES / module / DICTIONARY).exists(), (
        f"{module}: no {DICTIONARY} — the module's strings are still literals in the markup"
    )


@pytest.mark.parametrize("module", _modules(), ids=lambda value: value)
def test_composables_live_in_their_folder(module: str):
    at_root = sorted(path.name for path in (FEATURES / module).glob("use*.ts"))
    assert not at_root, f"{module}: composables sit in the folder root, they belong in composables/: {at_root}"


@pytest.mark.parametrize("module", _modules(), ids=lambda value: value)
def test_label_mapping_is_named_labels(module: str):
    """Turning backend codes into labels is the same job in every module, and the file has one
    name: ``labels.ts``. A name of its own in each module (``groupText`` / ``taskText`` /
    ``settingText``) hid the shared technique: it had to be found by content, not by name."""
    misnamed = sorted(path.name for path in (FEATURES / module).glob("*Text.ts"))
    assert not misnamed, f"{module}: the labels file is not named labels.ts: {misnamed}"
