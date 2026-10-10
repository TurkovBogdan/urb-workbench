"""The ``workbench`` server as a client sees it — pinned against a committed snapshot.

A connected client caches tool schemas at connect time: a renamed argument, a reworded refusal
in a description, a field dropped from an answer's schema breaks it while the write still lands.
So the whole listing — every tool with its name, description, input and output JSON schema, and
the server instructions — is compared with ``workbench_surface.json`` as a whole, not field by
field: a difference anywhere is a deployment decision, not a refactoring detail.

The server version is left out: it follows the release number, which changes on every release
without changing anything the agent reads.

A deliberate change to the surface regenerates the file:
``UPDATE_SURFACE_SNAPSHOT=1 uv run pytest tests/modules/workbench/test_surface_snapshot.py``,
and the diff of the JSON is what gets reviewed.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest
from fastmcp import Client
from fastmcp.server.middleware import Middleware

from src.core.mcp.context import McpServerContext
from src.modules.workbench.server import mcp_server

pytestmark = pytest.mark.pure

SNAPSHOT = Path(__file__).with_name("workbench_surface.json")


# Refusals the shared tools give by the code's TYPE alone, before any row is read — the texts the
# per-prefix registries assemble from what is registered, so their order and wording are pinned
# here with the schemas.
_DISPATCH_CALLS = (
    ("delete", {"code": "JOURNAL@0000000000"}),
    ("delete", {"code": "TASKGROUP@0000000000"}),
    ("delete", {"code": "GROUP@0000000000"}),
    ("delete", {"code": "WORKSPACE@0000000000"}),
    ("delete", {"code": "SOURCE@0000000000"}),
    ("interface_open", {"code": "SOURCE@0000000000"}),
    ("content_set", {"code": "SOURCE@0000000000", "field": "body", "text": "x"}),
    ("content_set", {"code": "WORKSPACE@0000000000", "field": "body", "text": "x"}),
    ("content_set", {"code": "TASK@0000000000", "field": "title", "text": "x"}),
    ("content_set", {"code": "TASK@0000000000", "field": "evidence", "text": "x"}),
    ("content_set", {"code": "STAGE@0000000000", "field": "evidence", "text": "x"}),
    ("content_set", {"code": "JOURNAL@0000000000", "field": "resolution", "text": "x"}),
    ("content_set", {"code": "NOTE@0000000000", "field": "title", "text": "x"}),
)


async def _surface() -> dict:
    server = mcp_server(McpServerContext(auth=None, audit=Middleware(), allowed_hosts=[]))
    async with Client(server) as client:
        tools = await client.list_tools()
        instructions = client.initialize_result.instructions
        refusals = []
        for name, arguments in _DISPATCH_CALLS:
            result = await client.call_tool(name, arguments, raise_on_error=False)
            refusals.append(
                {
                    "tool": name,
                    "arguments": arguments,
                    "refusal": "".join(block.text for block in result.content),
                }
            )
    return {
        "instructions": instructions,
        "tools": [tool.model_dump(mode="json", exclude_none=True) for tool in tools],
        "dispatch_refusals": refusals,
    }


async def test_the_surface_matches_the_snapshot():
    surface = await _surface()
    if os.environ.get("UPDATE_SURFACE_SNAPSHOT"):
        SNAPSHOT.write_text(
            json.dumps(surface, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
    assert surface == json.loads(SNAPSHOT.read_text(encoding="utf-8"))
