"""Nothing a page opened outlives the page: the KeepAlive overlay rule.

Every routed page lives in the global ``KeepAlive`` of ``App.vue``. Leaving a page does not
unmount it: its DOM moves into a detached container, and whatever it had put outside that DOM
stays on screen over the next page — the content of a ``Teleport to="body"``, an open Vuetify
tooltip, dialog or snackbar. The rule therefore sits in two places, and this file keeps both in
place:

- ``PageLayout``, the root of every routed page, owns the "page on screen" flag
  (``providePageActive``) and disables every overlay kind the app uses while its page is away —
  so every page must stand on it;
- a ``Teleport`` shows only while its page is active (``usePageActive``, or the editor toolbars'
  ``usePanelPlacement`` built on it).

What text cannot see — an overlay opened from code, a node view — is covered in the browser; the
checks are listed in the codex, ``/urb-core-template/shell/keepalive``.

Sources are read as text, as in the neighbouring ``test_web_*`` checks: no build, hence ``pure``.
The analysis behind the rule — AREA@1f55c60a67 in the research catalogue, TASK@230D528502.
"""

from __future__ import annotations

from pathlib import Path

import pytest

pytestmark = pytest.mark.pure

WEB_SRC = Path(__file__).resolve().parents[2] / "web" / "src"
PAGE_LAYOUT = WEB_SRC / "layout" / "templates" / "PageLayout.vue"

# Vuetify overlays the page frame disables while its page is away. `VMenu` closes itself on
# deactivation, but not in a Tiptap node view, which gets no KeepAlive hooks — so it is here too.
OVERLAYS = ("VTooltip", "VDialog", "VSnackbar", "VBottomSheet", "VMenu")

# What makes a teleported block follow its page's flag — a call, not a mention.
PAGE_FLAG_CALLS = ("usePageActive(", "usePanelPlacement(")

# Routed pages that do not stand on PageLayout, each with the reason it is safe.
PAGES_WITHOUT_LAYOUT = {
    # Draws itself full screen and opens no overlay.
    "views/errors/NotFoundView.vue",
    # A sheet of paper printed from a hidden frame, which no one navigates away from; the page
    # frame's scrolling zone would cut the print down to its first page.
    "features/codex/views/CodexPrintView.vue",
    "features/tasks/views/TaskNotePrintView.vue",
}


def _rel(path: Path) -> str:
    return path.relative_to(WEB_SRC).as_posix()


VUE_FILES = sorted(WEB_SRC.rglob("*.vue"))
PAGES = sorted([*WEB_SRC.glob("features/*/views/*.vue"), *(WEB_SRC / "views").rglob("*.vue")])
TELEPORTING = [path for path in VUE_FILES if "<Teleport" in path.read_text(encoding="utf-8")]


def test_the_checks_see_the_tree() -> None:
    # A renamed folder would turn every check below into a pass over nothing.
    assert len(PAGES) > 50
    assert TELEPORTING


@pytest.mark.parametrize("path", TELEPORTING, ids=_rel)
def test_a_teleport_shows_only_while_its_page_is_active(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    assert any(call in text for call in PAGE_FLAG_CALLS), (
        f"{_rel(path)}: <Teleport> without usePageActive — its content stays on screen after "
        "the page is left"
    )


def test_page_layout_hands_down_the_page_flag() -> None:
    assert "providePageActive()" in PAGE_LAYOUT.read_text(encoding="utf-8")


def test_page_layout_disables_every_overlay_in_use() -> None:
    layout = PAGE_LAYOUT.read_text(encoding="utf-8")
    used = {
        name
        for path in VUE_FILES
        if path != PAGE_LAYOUT
        for name in OVERLAYS
        if f"<{name}" in path.read_text(encoding="utf-8")
    }
    assert used, "no overlay found — the scan is broken"
    missing = sorted(name for name in used if f"{name}: {{ disabled }}" not in layout)
    assert not missing, f"PageLayout does not close these overlays on leaving the page: {missing}"


@pytest.mark.parametrize("path", PAGES, ids=_rel)
def test_every_page_stands_on_page_layout(path: Path) -> None:
    if _rel(path) in PAGES_WITHOUT_LAYOUT:
        return
    assert "<PageLayout" in path.read_text(encoding="utf-8"), (
        f"{_rel(path)}: a routed page without PageLayout keeps its overlays open after it is left"
    )


def test_exempt_pages_exist() -> None:
    for rel in PAGES_WITHOUT_LAYOUT:
        assert (WEB_SRC / rel).is_file(), f"stale exemption: {rel}"
