"""Sidebar sections: each has a code, and a menu entry names its section by that code.

A section used to be just a label in a flat list, and an entry's place was set by which lines it
sat next to. Now an entry declares its section (``section: '<code>'``) — which means a typo in the
code sends the entry into a section that does not exist, and it simply never shows in the menu:
neither the build nor the types catch it, since a section code is a plain string to them. The
second silent failure is the label: a section renders through ``t(labelKey)``, and a key without
a translation is shown in the menu as-is, as the key path.

The check lives in the Python tests for the same reason as its neighbours: the frontend has no
test runner, and the agreement has to be checkable. Sources are read as text, hence ``pure``; it
sits in ``apps`` because the rule is about the application shell as a whole.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

pytestmark = pytest.mark.pure

WEB_SRC = Path(__file__).resolve().parents[2] / "web" / "src"

SIDEBAR = WEB_SRC / "layout" / "components" / "AppSidebar.vue"
COMMON_LOCALE = WEB_SRC / "locales" / "ru.json"

# Section labels belong to the shell rather than a module, so they live in the common dictionary.
SECTION_LABEL_NAMESPACE = "common.nav."


def _array_literal(name: str) -> str:
    """The body of the array ``const <name> … = [ … ]``. The closing bracket is matched at the
    start of a line: an entry holds a nested ``children`` array, and its ``],`` is indented."""
    source = SIDEBAR.read_text(encoding="utf-8")
    match = re.search(rf"const {name}[^=]*= \[(.*?)\n\]", source, re.S)
    assert match, f"{name}: array not found — the test is looking in the wrong place"
    return match.group(1)


def _declared_sections() -> dict[str, str]:
    """Section code → its label key. The fields are read separately, not as a pair: their order
    inside an entry is a matter of taste, and a test tied to it would blame menu entries instead of
    sections."""
    sections = {}
    for entry in re.findall(r"\{[^{}]*\}", _array_literal("navSections")):
        code = re.search(r"code: '([^']+)'", entry)
        label_key = re.search(r"labelKey: '([^']+)'", entry)
        if code and label_key:
            sections[code.group(1)] = label_key.group(1)
    return sections


def _sections_named_by_entries() -> list[str]:
    return re.findall(r"section: '([^']+)'", _array_literal("navEntries"))


def _common_messages() -> dict:
    return json.loads(COMMON_LOCALE.read_text(encoding="utf-8"))


def test_the_menu_is_actually_parsed():
    """A silently green test is worse than none: if the regex stops seeing the lists, the failure
    must happen here, not half a year later as an empty menu."""
    assert len(_declared_sections()) >= 5
    assert len(_sections_named_by_entries()) >= 5


@pytest.mark.parametrize("section", sorted(set(_sections_named_by_entries())), ids=lambda value: value)
def test_entry_names_a_declared_section(section: str):
    assert section in _declared_sections(), f"{section}: menu entry in an undeclared section — it will not show"


@pytest.mark.parametrize("code,label_key", sorted(_declared_sections().items()), ids=lambda value: value)
def test_section_label_resolves(code: str, label_key: str):
    assert label_key.startswith(SECTION_LABEL_NAMESPACE), (
        f"{code}: a section label comes from the common dictionary, the key must be {SECTION_LABEL_NAMESPACE}*"
    )

    messages = _common_messages()
    for key in label_key.removeprefix("common.").split("."):
        assert isinstance(messages, dict) and key in messages, f"{code}: no translation for {label_key}"
        messages = messages[key]

    assert isinstance(messages, str) and messages, f"{code}: translation of {label_key} is empty"
