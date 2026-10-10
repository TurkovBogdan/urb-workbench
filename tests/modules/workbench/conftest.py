"""Fixtures for the ``workbench`` tests: a fresh in-memory DB with every schema the server reaches,
a workspace, and the server itself.

``db`` builds the schema from the ORM models (``create_all``) on a new ``:memory:`` database —
migrations are not applied here, they belong to the heavy tier. The server reaches the tables of
every domain module below it, so their models are imported here: without an FK target in the
metadata ``create_all`` fails with ``NoReferencedTableError`` — a full run hides this (another
module has already pulled its models in), a single-module run catches it at once.

``workspace`` spares almost every test the same first line: neither a group nor a task can be
created without a workspace. The row is created by the ``workspace`` module's CRUD — the path the
application takes.

``mcp``/``call`` bring the ``workbench`` MCP server up in-memory: tools are called exactly as the
agent sees them (``@`` prefixes in codes, DTOs, ``ToolError`` errors). This client has no HTTP
request, so every call in a test shares one session — the common local key (``session.py``).
That is both convenient (the binding holds across calls within a test) and a limitation: that
the session header arrives at all and that two sessions do not see each other cannot be checked
in-memory — ``test_mcp_session_http.py`` does that.
"""

from __future__ import annotations

import pytest
from fastmcp import Client
from fastmcp.server.middleware import Middleware

from src.core.config import Config
from src.core.database import close_database, init_database
from src.core.mcp.context import McpServerContext
from src.modules.workbench.server import mcp_server
from src.modules.workspace.crud.workspace import workspace_create


@pytest.fixture
async def db(config: Config):
    engine = await init_database(config)
    from src.core.database.runtime import Base
    import src.modules.notes.models  # noqa: F401 — the ``note_code`` FK target of task notes
    import src.modules.tasks.models  # noqa: F401 — registers the tasks tables
    import src.modules.workspace.models  # noqa: F401 — the ``workspace_code`` FK target

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    try:
        yield
    finally:
        await close_database()


@pytest.fixture
async def workspace(db):
    """A live workspace — the root everything else hangs off."""
    return await workspace_create(title="Работа")


@pytest.fixture
async def mcp(db):
    """The ``workbench`` MCP server in-memory: auth off, audit a no-op."""
    server = mcp_server(McpServerContext(auth=None, audit=Middleware(), allowed_hosts=[]))
    async with Client(server) as c:
        yield c


@pytest.fixture
def call(mcp):
    """Call a tool and return ``structured_content``. A rule refusal → ``ToolError``."""

    async def _call(name: str, **args):
        return (await mcp.call_tool(name, args)).structured_content

    return _call
