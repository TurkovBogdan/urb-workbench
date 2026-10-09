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
"""

from __future__ import annotations

import asyncio
import webbrowser
from typing import TYPE_CHECKING

from src.core.config import get_config
from src.modules.tasks.codes import bare_code, code_prefix, tagged
from src.modules.tasks.constants import (
    GROUP_CODE_PREFIX,
    JOURNAL_CODE_PREFIX,
    NOTE_CODE_PREFIX,
    STAGE_CODE_PREFIX,
    TASK_CODE_PREFIX,
)
from src.modules.notes.crud import note as notes_crud
from src.modules.tasks.crud import journal as journal_crud
from src.modules.tasks.crud import note as note_crud
from src.modules.tasks.crud import stage as stage_crud
from src.modules.tasks.mcp.scope import require_scope
from src.modules.workspace.constants import WORKSPACE_CODE_PREFIX

if TYPE_CHECKING:  # fastmcp fork — backend only (via mcp_server(ctx))
    from fastmcp import FastMCP

# List pages: a workspace and a group have no card page of their own, they live as rows in their
# lists. Opening the list is exactly "show me where it is".
_LIST_PAGE = {
    WORKSPACE_CODE_PREFIX: "/workspaces",
    GROUP_CODE_PREFIX: "/tasks/groups",
}

_OPENABLE = (
    WORKSPACE_CODE_PREFIX,
    GROUP_CODE_PREFIX,
    TASK_CODE_PREFIX,
    STAGE_CODE_PREFIX,
    JOURNAL_CODE_PREFIX,
    NOTE_CODE_PREFIX,
)


async def _owning_task(prefix: str, bare: str) -> str:
    """The task that owns a stage or a journal entry."""
    if prefix == STAGE_CODE_PREFIX:
        row = await stage_crud.stage_get(bare)
    else:
        row = await journal_crud.journal_get(bare)
    if row is None:
        raise ValueError(f"{tagged(prefix, bare)} does not exist.")
    return row.task_code


async def _note_page(bare: str) -> str:
    """The page of a note — decided by what the note belongs to.

    A note of the ``notes`` module does not know its owner; each owner holds its own link. So the
    owners are asked in turn, and the first that holds the note gives the address inside its own
    page. Today that is a task; a knowledge base, when it comes, answers here with its own page.
    A deleted note has no page to show — its owner's page lists it no more.
    """
    code = tagged(NOTE_CODE_PREFIX, bare)
    if await notes_crud.note_get(bare) is None:
        raise ValueError(f"{code} does not exist (or is deleted) — there is no page to show.")
    task = await note_crud.task_note_task(bare)
    if task is not None:
        return f"/tasks/task/{tagged(TASK_CODE_PREFIX, task)}/note/{code}"
    # Held by no owner this server knows: for the agent it does not exist, as for the other tools.
    raise ValueError(f"{code} does not exist (or is deleted) — there is no page to show.")


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
        of their own. A NOTE@ opens its own page, inside its task's. A WORKSPACE@ or a TASKGROUP@
        opens the list it is a row in.

        It acts on the user's machine, so do it when it was asked for or clearly helps, not
        after every call.

        Args:
            code: What to show — a TASK@, STAGE@, JOURNAL@, NOTE@, TASKGROUP@ or WORKSPACE@ code.
        """
        prefix = code_prefix(code)
        if prefix not in _OPENABLE:
            raise ValueError(
                f"{code!r} is not something with a page — pass a "
                f"{' / '.join(f'{p}@' for p in _OPENABLE)} code."
            )
        bare = bare_code(code, prefix) or ""
        await require_scope(prefix, bare)
        if prefix in _LIST_PAGE:
            path = _LIST_PAGE[prefix]
        elif prefix == NOTE_CODE_PREFIX:
            path = await _note_page(bare)
        else:
            task = bare if prefix == TASK_CODE_PREFIX else await _owning_task(prefix, bare)
            path = f"/tasks/task/{tagged(TASK_CODE_PREFIX, task)}"
        url = _app_url(path)
        # Launching a browser is a synchronous call of unknown duration (process spawn, cold
        # start): run it in a thread so it does not hold the server's event loop.
        if not await asyncio.to_thread(webbrowser.open, url):
            raise ValueError(f"No browser to open on this host — give the user {url} instead.")
        return url


__all__ = ["register"]
