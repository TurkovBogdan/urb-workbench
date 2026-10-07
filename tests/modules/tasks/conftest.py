"""Fixtures for the ``tasks`` tests: a fresh in-memory DB with the module schema, a workspace, an
HTTP client.

``db`` builds the schema from the ORM models (``create_all``) on a new ``:memory:`` database —
migrations are not applied here, they belong to the heavy tier. The ``workspace`` models are
imported next to ours: groups and tasks have an FK to ``workspaces``, and without the target in
the metadata ``create_all`` fails with ``NoReferencedTableError`` — a full run hides this
(another module has already pulled its models in), a single-module run catches it at once.

``workspace`` spares almost every db test the same first line: neither a group nor a task can be
created without a workspace. The row is created by the neighbouring module's CRUD — we no longer
have an endpoint of our own, and substituting a direct insert would test a path other than the
one the application takes.

``app``/``client`` mount the module router on a bare ``FastAPI`` rather than via ``create_app``:
the tests are about the module's routes, and there is no reason to drag in the application
lifecycle for them. The one thing that has to be added by hand is
``register_exception_handlers``: without it ``ApiError`` flies past the handler, and instead of a
404 with an ``{"error": …}`` body the test would get an exception
(see ``docs/platform/api-zones.md``). They live here rather than in one test file: the module now
has three surfaces (workspaces, groups, tasks), and a second copy of the app setup would drift
from the first on the very first change.

``mcp``/``call`` are the module's second surface, the ``workbench`` MCP server brought up
in-memory: tools are called exactly as the agent sees them (``@`` prefixes in codes, DTOs,
``ToolError`` errors). This client has no HTTP request, so every call in a test shares one
session — the common local key (``workspace/mcp/session.py``). That is both convenient (the
binding holds across calls within a test) and a limitation: that the session header arrives at
all and that two sessions do not see each other cannot be checked in-memory —
``test_mcp_session_http.py`` does that.
"""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastmcp import Client
from fastmcp.server.middleware import Middleware
from httpx import ASGITransport, AsyncClient

from src.core.api import register_exception_handlers
from src.core.config import Config
from src.core.database import close_database, init_database
from src.core.mcp.context import McpServerContext
from src.modules.tasks.api import router
from src.modules.tasks.mcp import mcp_server
from src.modules.workspace.crud.workspace import workspace_create


@pytest.fixture
async def db(config: Config):
    engine = await init_database(config)
    from src.core.database.runtime import Base
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
async def app(config: Config):
    engine = await init_database(config)
    from src.core.database.runtime import Base
    import src.modules.tasks.models  # noqa: F401 — registers the tasks tables
    import src.modules.workspace.models  # noqa: F401 — the ``workspace_code`` FK target

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    fastapi_app = FastAPI()
    register_exception_handlers(fastapi_app)
    # The prefix mirrors production (``TasksModule.internal_router_prefix``): ``/workbench``, not
    # ``/tasks``, because the ``/internal/tasks`` root is taken by the ``core_monitoring`` schedule.
    fastapi_app.include_router(router, prefix="/internal/workbench")
    try:
        yield fastapi_app
    finally:
        await close_database()


@pytest.fixture
async def client(app):
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as c:
        yield c


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
