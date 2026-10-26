"""The display MCP tool — open an entity's page in the user's browser.

The only bridge from "agent" to "the person's eyes": a code becomes the address of an app page
and is opened in the local browser. The app is local and the backend serves the built SPA
itself, so the address is built from ``server_host``/``server_port`` — the same base url the
stdio shim opens.

Not everything has a page of its own. A stage and a journal entry live on their task's page,
and
a code of that type leads there too — we resolve the owner and open it. Refusing here would be
pedantry: the agent asks to show the work, not an address.

The workspace fence applies here as well. Opening a page is a visible action on the person's
machine, and silently showing them another workspace would make a boundary error, on top of
everything, visible to the wrong eyes.

Which path shows a type, and whether its code is visible from here, is its handler's
(``contracts.Openable``) — registered in ``OPENABLE`` by prefix; the order there is the order the
refusal lists the types in.
"""

from __future__ import annotations

import asyncio
import webbrowser
from typing import TYPE_CHECKING

from src.core.config import get_config
from src.modules.workbench.codes import bare_code, code_prefix
from src.modules.workbench.contracts import Openable, by_prefix
from src.modules.workbench.entities.codex import CodexPage
from src.modules.workbench.entities.file import FilePage, as_file_code
from src.modules.workbench.entities.tasks import (
    GroupPage,
    JournalPage,
    NotePage,
    StagePage,
    TaskPage,
)
from src.modules.workbench.entities.workspace import WorkspacePage
from src.modules.workbench.scope import require_visible

if TYPE_CHECKING:  # fastmcp fork — backend only (via mcp_server(ctx))
    from fastmcp import FastMCP

OPENABLE: dict[str, Openable] = by_prefix(
    WorkspacePage(),
    GroupPage(),
    TaskPage(),
    StagePage(),
    JournalPage(),
    NotePage(),
    CodexPage(),
    FilePage(),
)


def _app_url(path: str) -> str:
    config = get_config()
    host = config.server_host if config.server_host not in ("", "0.0.0.0") else "127.0.0.1"
    return f"http://{host}:{config.server_port}{path}"


def register(mcp: "FastMCP") -> None:

    @mcp.tool()
    async def interface_open(code: str) -> str:
        """Open the page for a code in the user's browser and return its address.

        This is how you SHOW something instead of describing it. Use it when the user asks to
        see something, and when you have finished a piece of work worth looking at — it puts the
        thing on screen rather than a paragraph about it. Returning the address also lets you
        paste it into the conversation.

        A STAGE@ or a JOURNAL@ opens the task it belongs to: they live on its page and have none
        of their own. A NOTE@ opens its own page, inside its task's. A CODEX@ opens the codex
        editor on that codex or note. A WORKSPACE@ or a TASKGROUP@ opens the list it is a row in.
        A FILE@ opens the file itself.

        It acts on the user's machine, so do it when it was asked for or clearly helps, not
        after every call.

        Args:
            code: What to show — a TASK@, STAGE@, JOURNAL@, NOTE@, CODEX@, TASKGROUP@,
                WORKSPACE@ or FILE@ code (an IMAGE@ names the same file).
        """
        code = as_file_code(code)
        prefix = code_prefix(code)
        handler = OPENABLE.get(prefix)
        if handler is None:
            raise ValueError(
                f"{code!r} is not something with a page — pass a "
                f"{' / '.join(f'{p}@' for p in OPENABLE)} code."
            )
        bare = bare_code(code, prefix) or ""
        await require_visible(handler, bare)
        url = _app_url(await handler.page(bare))
        # Launching a browser is a synchronous call of unknown duration (process spawn, cold
        # start): run it in a thread so it does not hold the server's event loop.
        if not await asyncio.to_thread(webbrowser.open, url):
            raise ValueError(f"No browser to open on this host — give the user {url} instead.")
        return url


__all__ = ["OPENABLE", "register"]
