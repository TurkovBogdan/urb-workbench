"""The page frame standard: every SPA view has one, and it sits above the content.

There are two frames, by kind of page. A **list** opens with a ``PageHeader``: the section name
there is the page title, and it carries the frame itself. A **detail** page carries no frame at
all: the sticky column lives in the shared ``DetailShell`` template, which sits on the parent
route and survives moving from artifact to artifact — only the content on the right changes.
Instead of a frame, a detail page FILLS the column by calling ``useDetailRail``, and that call is
also what marks its kind here.

Both cases share one thing: the frame is the first thing seen. Let a page go without one (or put
it after the content), and moving to that page reads as a jump.

The check lives in the Python tests rather than the frontend for a prosaic reason: the frontend
has no test runner, and the convention has to be checkable. Sources are read as text — no build
or browser needed, hence ``pure``. It sits in ``apps``: the rule is about the application as a
whole, not a single module, and this way it lands in the regular ``--core`` run.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

pytestmark = pytest.mark.pure

WEB_SRC = Path(__file__).resolve().parents[2] / "web" / "src"

# Pages without a header are only those with no page frame at all:
# home (a full-screen welcome showcase) and the "not found" screen (it draws itself).
EXEMPT = {
    "views/HomeView.vue",
    "views/errors/NotFoundView.vue",
    # The print version of a research page: it has no frame by design — it is a document for
    # paper, not a screen with navigation. It is also unreachable: the `research` module was
    # removed (2026-09-20), its route is registered nowhere, and the `features/research` folder
    # lives on only because the design-system showcase shows two of its cards. Drop this line
    # together with the folder.
    "features/research/views/ResearchPrintView.vue",
}

PAGE_FRAME = "<PageHeader"

# The detail frame template: carried by the parent route, not by the view.
DETAIL_SHELL = WEB_SRC / "layout" / "templates" / "DetailShell.vue"

# The detail mark: the page fills the shared frame's column instead of drawing its own.
# We match the IMPORT, not the call: the design-system showcase shows the same call as a string in
# a code example, and by the call it would count as a detail page, which it is not.
DETAIL_MARK = "@/layout/detailRail"

# Having a frame is not enough: it must sit ABOVE the content, so we compare against the start of
# whatever content usually opens with. A refusal (``SectionError``) is not included — it is not
# page content but a message in its place, and on a detail page it comes before the column.
CONTENT_OPENERS = (
    "<VCard",
    "<VDataTable",
    "<VAlert",
    "<section",
    "<SectionHeader",
)


def _template(source: str) -> str:
    """The view's markup without ``<script>``: the script holds the design-system showcase's code
    examples, and they contain both ``<PageHeader`` and a whole ``<template>`` — from those the
    test would credit the view with a frame the page does not have, or take an example for the
    markup itself. So the script is cut out ENTIRELY, and only then is the template looked for."""
    markup = re.sub(r"<script.*?</script>", "", source, flags=re.S)
    match = re.search(r"<template>(.*)</template>", markup, re.S)
    return match.group(1) if match else ""


def _is_page(name: str) -> bool:
    """A view is a file in a ``views/`` folder, not everything ending in ``View.vue``.

    The name pattern swept in ``components/markdown/editor/EntityRefView.vue`` — a Tiptap editor
    node that renders an entity link INSIDE text. It has no page frame and cannot have one, so the
    test demanded the impossible of it and was always red. A page route always points at a file
    in ``views/``, so the folder is an exact mark and the suffix is not.
    """
    return "views/" in name


def _views() -> list[tuple[str, str]]:
    found = []
    for path in sorted(WEB_SRC.rglob("*View.vue")):
        name = path.relative_to(WEB_SRC).as_posix()
        if _is_page(name) and name not in EXEMPT:
            found.append((name, path.read_text(encoding="utf-8")))
    return found


def test_every_view_is_covered_by_the_check():
    """The walk itself: if views stop being found, a silently green test is worse than none."""
    assert len(_views()) > 40


@pytest.mark.parametrize("name,source", _views(), ids=lambda value: value if isinstance(value, str) and value.endswith(".vue") else "")
def test_view_starts_with_its_page_frame(name: str, source: str):
    if DETAIL_MARK in source:
        return

    template = _template(source)
    assert PAGE_FRAME in template, f"{name}: page without a frame — moving to it reads as a jump"

    frame_at = template.index(PAGE_FRAME)
    for opener in CONTENT_OPENERS:
        content_at = template.find(opener)
        if content_at != -1:
            assert frame_at < content_at, f"{name}: the frame sits below the content ({opener})"


@pytest.mark.parametrize("name,source", _views(), ids=lambda value: value if isinstance(value, str) and value.endswith(".vue") else "")
def test_detail_page_leaves_the_frame_to_the_shell(name: str, source: str):
    """A detail page draws neither a column nor a header: both belong to the shared frame. Its own
    column would vanish on every navigation, and a second header on top would bring back exactly
    the split the column was introduced to get away from."""
    if DETAIL_MARK not in source:
        return

    template = _template(source)
    for own_frame in ("<PageHeader", "<PageLayout", "<DetailLayout", "<DetailNav"):
        assert own_frame not in template, f"{name}: detail page draws {own_frame} — the frame is doubled"


def test_detail_shell_carries_the_frame():
    """There is one detail frame for all, and it must carry both parts: the column with the way
    out and the slot for content. If the template lost either, pages would lose their way out,
    and no test above would notice: they look at views, and views no longer carry the frame."""
    shell = _template(DETAIL_SHELL.read_text(encoding="utf-8"))

    assert "<DetailLayout" in shell, "DetailShell: frame without a column"
    assert "<DetailNav" in shell, "DetailShell: column without a way out of the page"
    assert "<RouterView" in shell, "DetailShell: the frame has nowhere to put the content"


def test_exempt_pages_still_exist():
    """Exemptions are listed by name: rename a page and the rule silently stops applying to it,
    and that must fail here rather than surface half a year later."""
    for name in EXEMPT:
        assert (WEB_SRC / name).exists(), f"{name}: listed as exempt, but no such file exists"
