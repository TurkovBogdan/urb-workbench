"""workbench MCP over a REALLY mounted server: does the session header get through.

The test the whole construction was built for. The in-memory client is blind to this: it has no
HTTP request, hence no headers, and all calls share one local key. Here the server is brought up
the same way as in the application (``mount_mcp_servers`` → an ASGI sub-app at ``/mcp/workbench``,
``stateless_http``), and the client reaches it through an ASGI transport with its own headers —
exactly what the shim does.

We check three things that cannot be checked anywhere else: the header gets through and the
binding keyed by it holds; **two sessions do not see each other's choice**; the workspace from
the launch config acts as the default, and the session's choice overrides it.
"""

from __future__ import annotations

import asyncio
from contextlib import AsyncExitStack

import pytest
from fastapi import FastAPI
from fastmcp import Client
from fastmcp.client.transports import StreamableHttpTransport
from httpx import ASGITransport, AsyncClient

from src.core.config import Config
from src.core.database import close_database, init_database
from src.core.mcp_headers import MCP_SESSION_HEADER, MCP_WORKSPACE_HEADER
from src.core.module import Module
from src.core.router.mcp import mount_mcp_servers
from src.modules.tasks import TasksModule
from src.modules.tasks.crud import group as group_crud
from src.modules.workspace.crud.workspace import workspace_create

pytestmark = pytest.mark.db

_URL = "http://test/mcp/workbench/"


class _Principal:
    """A duck-typed principal: the verifier needs only ``id`` and ``group``."""

    id = 0
    group = "test"


class _AuthModule(Module):
    """Provider of the single ``mcp_token_resolver``: without one, mounting refuses.

    In the application ``research`` holds this role for now (a stub until an auth module), but
    pulling a foreign module here with all its tables would test its assembly, not our header.
    Everyone is let in: the test is about the session header, not the bearer —
    ``tests/core/test_mcp_server_auth.py`` covers that.
    """

    name = "test_auth"

    @staticmethod
    async def resolve(token: str, scope: str):
        return _Principal()

    mcp_token_resolver = staticmethod(resolve)


@pytest.fixture
async def mounted(config: Config):
    """FastAPI with ``workbench`` mounted and the sub-apps' lifespans entered.

    The lifespan is mandatory: without it the fork's session manager is not initialized and any
    call answers 500. In the application ``create_app`` enters them; here a separate task does.

    A task rather than ``async with`` right in the fixture: the fork's lifespan holds an anyio
    scope, which requires entry and exit to happen in the SAME task. pytest finalizes an
    async-generator fixture in a different one, and the exit would fail with "exit cancel scope
    in a different task" — on green tests, which is worse than red ones.
    """
    engine = await init_database(config)
    from src.core.database.runtime import Base
    import src.modules.tasks.models  # noqa: F401 — registers the tasks tables
    import src.modules.workspace.models  # noqa: F401 — the ``workspace_code`` FK target

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    app = FastAPI()
    lifespans = mount_mcp_servers(app, [_AuthModule(), TasksModule()], config)
    up, down = asyncio.Event(), asyncio.Event()

    async def hold() -> None:
        async with AsyncExitStack() as stack:
            for lifespan in lifespans:
                await stack.enter_async_context(lifespan)
            up.set()
            await down.wait()

    holder = asyncio.create_task(hold())
    await up.wait()
    try:
        yield app
    finally:
        down.set()
        await holder
        await close_database()


def _session(app: FastAPI, **headers: str) -> Client:
    """A client with its own headers — the same way the shim sets them on its transport.

    ``auth`` is mandatory: without ``Authorization`` the fork answers 401 before reaching the
    tools, never asking the resolver. The shim passes ``MCP_TOKEN`` here; our stub accepts any.
    """

    def factory(**kwargs):
        kwargs.pop("timeout", None)
        return AsyncClient(transport=ASGITransport(app=app), base_url="http://test", **kwargs)

    return Client(
        StreamableHttpTransport(
            _URL, headers=headers, auth="test-token", httpx_client_factory=factory
        )
    )


async def _titles(client: Client) -> list[str]:
    answer = await client.call_tool("groups_list", {})
    return [group["title"] for group in answer.structured_content["groups"]]


async def test_the_session_header_carries_the_binding_across_calls(mounted):
    """The binding is set by one call and lives on in the next — though the server is stateless."""
    work = await workspace_create(title="Работа")
    await group_crud.group_create(workspace_code=work.code, title="Биллинг")

    async with _session(mounted, **{MCP_SESSION_HEADER: "session-one"}) as client:
        await client.call_tool("workspace_use", {"workspace_code": work.code})
        assert await _titles(client) == ["Биллинг"]


async def test_two_sessions_do_not_see_each_others_choice(mounted):
    """The reason the header exists: a neighbouring connection does not move your workspace."""
    work = await workspace_create(title="Работа")
    home = await workspace_create(title="Личное")
    await group_crud.group_create(workspace_code=work.code, title="Биллинг")
    await group_crud.group_create(workspace_code=home.code, title="Ремонт")

    async with _session(mounted, **{MCP_SESSION_HEADER: "session-one"}) as one:
        await one.call_tool("workspace_use", {"workspace_code": work.code})
        async with _session(mounted, **{MCP_SESSION_HEADER: "session-two"}) as two:
            await two.call_tool("workspace_use", {"workspace_code": home.code})
            assert await _titles(two) == ["Ремонт"]
        # The first session learns of the second one's choice only in that nothing changed.
        assert await _titles(one) == ["Биллинг"]


async def test_the_configured_workspace_binds_a_fresh_session(mounted):
    """A connection configured with a workspace works without a single selection call."""
    work = await workspace_create(title="Работа")
    await group_crud.group_create(workspace_code=work.code, title="Биллинг")

    headers = {MCP_SESSION_HEADER: "fresh", MCP_WORKSPACE_HEADER: f"WORKSPACE@{work.code}"}
    async with _session(mounted, **headers) as client:
        assert await _titles(client) == ["Биллинг"]


async def test_the_session_choice_overrides_the_configured_default(mounted):
    """A default is a default: the agent's choice wins and does not touch the settings file."""
    work = await workspace_create(title="Работа")
    home = await workspace_create(title="Личное")
    await group_crud.group_create(workspace_code=home.code, title="Ремонт")

    headers = {MCP_SESSION_HEADER: "override", MCP_WORKSPACE_HEADER: work.code}
    async with _session(mounted, **headers) as client:
        await client.call_tool("workspace_use", {"workspace_code": home.code})
        assert await _titles(client) == ["Ремонт"]


async def test_a_garbled_configured_workspace_does_not_break_the_server(mounted):
    """A typo in an OPTIONAL setting must not bring the server down — it yields a plain refusal."""
    await workspace_create(title="Работа")

    headers = {MCP_SESSION_HEADER: "garbled", MCP_WORKSPACE_HEADER: "TASKGROUP@0000000000"}
    async with _session(mounted, **headers) as client:
        answer = await client.call_tool("workspaces_list", {})
        assert [row["active"] for row in answer.structured_content["result"]] == [False]
