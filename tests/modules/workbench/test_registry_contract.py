"""The shared methods' registries accept a handler that answers both questions itself.

``content_*``, ``delete``, ``interface_open`` and the fence dispatch by code prefix to a handler,
and the handler — not the tool — finds the row by the code and decides whether the code is
visible in the active workspace. That is what a type unlike the task family needs: the codex
(TASK@8B21CF0C62) keeps one ``CODEX@`` prefix over two tables, and a codex is attached to several
workspaces, so "visible here" is not "owner == active".

The stub below is that shape: rows in two dicts under one prefix, each row visible in a set of
workspaces. It is registered into the live registries for one test at a time, and the tools are
called exactly as the agent calls them.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastmcp.exceptions import ToolError

from src.modules.workbench.content.base import McpContentHandler
from src.modules.workbench.content.registry import MCP_CONTENT_HANDLERS
from src.modules.workbench.contracts import Deletable, Fence, Openable
from src.modules.workbench.scope import FENCES, require_scope
from src.modules.workbench.tools.delete import DELETABLE
from src.modules.workbench.tools.interface import OPENABLE
from src.modules.workspace.crud.workspace import workspace_create
from src.modules.workspace.models.workspace import Workspace

pytestmark = pytest.mark.db

PREFIX = "STUB"


class _Shelf:
    """The stub's storage: two tables under one prefix, and who may see each row."""

    def __init__(self) -> None:
        self.books: dict[str, SimpleNamespace] = {}
        self.pages: dict[str, SimpleNamespace] = {}
        self.seen_in: dict[str, set[str]] = {}
        self.lookups: list[str] = []

    def find(self, bare: str) -> SimpleNamespace | None:
        self.lookups.append(bare)
        return self.books.get(bare) or self.pages.get(bare)


class _StubVisibility(Fence):
    prefix = PREFIX
    shelf: _Shelf

    async def require_visible(self, bare: str, active: Workspace) -> None:
        seen_in = self.shelf.seen_in.get(bare)
        if seen_in is not None and active.code not in seen_in:
            raise ValueError(f"{PREFIX}@{bare} is not attached to {active.title!r}.")


class _StubBody(_StubVisibility, McpContentHandler):
    field = "body"
    limit = 100
    what = "the stub body"

    async def load(self, s, bare: str):
        return self.shelf.find(bare)


class _StubDeletion(_StubVisibility, Deletable):
    async def delete(self, bare: str) -> bool:
        return self.shelf.books.pop(bare, None) is not None or (
            self.shelf.pages.pop(bare, None) is not None
        )


class _StubPage(_StubVisibility, Openable):
    async def page(self, bare: str) -> str:
        return f"/stub/{bare}" if self.shelf.find(bare) else "/stub"


@pytest.fixture
async def shelf(monkeypatch, workspace) -> _Shelf:
    """A shelf with a row in each table: ``BOOK`` seen here and elsewhere, ``PAGE`` only here,
    ``AWAY`` only in another workspace."""
    elsewhere = await workspace_create(title="Личное")
    shelf = _Shelf()
    shelf.books["BOOK"] = SimpleNamespace(body="книга")
    shelf.pages["PAGE"] = SimpleNamespace(body="страница")
    shelf.books["AWAY"] = SimpleNamespace(body="чужое")
    shelf.seen_in = {
        "BOOK": {workspace.code, elsewhere.code},
        "PAGE": {workspace.code},
        "AWAY": {elsewhere.code},
    }
    for handler_class in (_StubBody, _StubDeletion, _StubPage, _StubVisibility):
        monkeypatch.setattr(handler_class, "shelf", shelf, raising=False)
    monkeypatch.setitem(FENCES, PREFIX, _StubVisibility())
    monkeypatch.setitem(MCP_CONTENT_HANDLERS, (PREFIX, "body"), _StubBody())
    monkeypatch.setitem(DELETABLE, PREFIX, _StubDeletion())
    monkeypatch.setitem(OPENABLE, PREFIX, _StubPage())
    monkeypatch.setattr(
        "src.modules.workbench.tools.interface.webbrowser.open", lambda url: True
    )
    return shelf


@pytest.fixture
async def bound(call, workspace, shelf):
    await call("workspace_use", workspace_code=workspace.code)
    return shelf


# ── content ───────────────────────────────────────────────────────────────────


@pytest.mark.parametrize("bare", ["BOOK", "PAGE"])
async def test_content_reaches_a_row_in_either_table(call, bound, bare):
    answer = await call(
        "content_add", code=f"stub@{bare.lower()}", field="body", text="!", position="end"
    )

    assert answer["code"] == f"{PREFIX}@{bare}"
    row = bound.books.get(bare) or bound.pages.get(bare)
    assert row.body.endswith("!")
    assert bound.lookups == [bare]


async def test_content_asks_the_handler_whether_the_code_is_visible(call, bound):
    with pytest.raises(ToolError, match="STUB@AWAY is not attached to 'Работа'"):
        await call("content_set", code="STUB@AWAY", field="body", text="переписано")

    assert bound.books["AWAY"].body == "чужое"


async def test_a_code_the_handler_does_not_find_is_not_found(call, bound):
    with pytest.raises(ToolError, match="STUB@NONE does not exist"):
        await call("content_set", code="STUB@NONE", field="body", text="х")


async def test_the_handler_s_limit_applies(call, bound):
    with pytest.raises(ToolError, match="limit is 100"):
        await call("content_set", code="STUB@BOOK", field="body", text="я" * 101)

    assert bound.books["BOOK"].body == "книга"


async def test_a_registered_type_joins_the_content_refusal(call, bound):
    with pytest.raises(ToolError, match="TASK@ / STAGE@ / JOURNAL@ / NOTE@ / STUB@ codes"):
        await call("content_set", code="SOURCE@1", field="body", text="х")


# ── delete ────────────────────────────────────────────────────────────────────


async def test_delete_goes_to_the_handler(call, bound):
    answer = await call("delete", code="STUB@PAGE")

    assert answer["result"] is True
    assert "PAGE" not in bound.pages


async def test_delete_refuses_what_the_handler_says_is_not_visible(call, bound):
    with pytest.raises(ToolError, match="not attached"):
        await call("delete", code="STUB@AWAY")

    assert "AWAY" in bound.books


# ── interface_open ────────────────────────────────────────────────────────────


async def test_interface_open_takes_the_handler_s_page(call, bound):
    answer = await call("interface_open", code="STUB@BOOK")

    assert answer["result"].endswith("/stub/BOOK")


async def test_interface_open_refuses_what_the_handler_says_is_not_visible(call, bound):
    with pytest.raises(ToolError, match="not attached"):
        await call("interface_open", code="STUB@AWAY")


# ── the fence ─────────────────────────────────────────────────────────────────


async def test_the_fence_registry_asks_the_handler_too(call, bound):
    active = await require_scope(PREFIX, "BOOK")
    assert active.title == "Работа"

    with pytest.raises(ValueError, match="not attached"):
        await require_scope(PREFIX, "AWAY")


def test_two_handlers_for_one_prefix_are_a_wiring_error():
    """A second handler for a prefix would silently replace the first in a plain dict — the
    codex's two tables must share ONE handler, not register two."""
    from src.modules.workbench.contracts import by_prefix

    first, second = _StubVisibility(), _StubVisibility()

    with pytest.raises(RuntimeError, match=f"{PREFIX}@"):
        by_prefix(first, second)
    assert by_prefix(first) == {PREFIX: first}
