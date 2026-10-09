"""The design-system showcase: every page has both a view and its strings.

A showcase page is registered in three places at once — route, index tile, dictionary. Forgetting
one of the three is easy, and a dictionary miss is silent: `vue-i18n` renders the key itself, so
the page opens and looks almost normal. Hence the link is checked here.

Sources are read as text — no build, no browser, hence the test is ``pure``.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

pytestmark = pytest.mark.pure

WEB_SRC = Path(__file__).resolve().parents[2] / "web" / "src"
ROUTES = WEB_SRC / "router" / "design-system.ts"
INDEX_VIEW = WEB_SRC / "views" / "design-system" / "DesignSystemIndexView.vue"
STRINGS = WEB_SRC / "locales" / "design-system" / "ru.json"


def _pages() -> list[tuple[str, str]]:
    """``slug → view path`` from the ``PAGES`` table of the showcase router."""
    table = re.search(r"const PAGES[^{]*\{(.*?)\n\}", ROUTES.read_text(encoding="utf-8"), re.S)
    assert table, "showcase page table not found — the tests below would go silently green"
    return re.findall(r"^\s*'?([\w-]+)'?:\s*'([\w/]+)',", table.group(1), re.M)


def _strings() -> dict:
    return json.loads(STRINGS.read_text(encoding="utf-8"))


def test_pages_are_found():
    assert len(_pages()) > 20


@pytest.mark.parametrize("slug,view", _pages(), ids=lambda value: value)
def test_page_has_its_view(slug: str, view: str):
    assert (WEB_SRC / "views" / "design-system" / f"{view}.vue").exists()


@pytest.mark.parametrize("slug,view", _pages(), ids=lambda value: value)
def test_page_has_its_strings(slug: str, view: str):
    strings = _strings()
    tile = strings["index"]["page"].get(slug)
    page = strings["page"].get(slug)

    assert tile and tile.get("label"), f"{slug}: showcase tile without a label"
    assert page and page.get("title") and page.get("description"), f"{slug}: page without a name"


@pytest.mark.parametrize("slug,view", _pages(), ids=lambda value: value)
def test_page_is_listed_on_the_index(slug: str, view: str):
    """A route without a tile is a page reachable only by a direct link."""
    assert f"slug: '{slug}'" in INDEX_VIEW.read_text(encoding="utf-8")


def _value_at(strings: dict, key: str):
    node = strings
    for step in key.split("."):
        if not isinstance(node, dict) or step not in node:
            return None
        node = node[step]
    return node


@pytest.mark.parametrize("slug,view", _pages(), ids=lambda value: value)
def test_page_asks_only_for_strings_it_has(slug: str, view: str):
    """A missing key does not break the page — `vue-i18n` renders the key itself, and the text
    "section.rule_note" in the middle of the showcase gets noticed a week later at best. Keys
    assembled in place (a template string inside `t(...)`) are not covered — their value is known
    only at runtime."""
    source = (WEB_SRC / "views" / "design-system" / f"{view}.vue").read_text(encoding="utf-8")
    strings = _strings()

    for key in re.findall(r"t\('design-system\.([\w.-]+)'\)", source):
        assert _value_at(strings, key) is not None, f"{view}: no string design-system.{key}"
