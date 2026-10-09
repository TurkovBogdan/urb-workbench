"""create_app: composition root + lifespan."""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from pydantic_settings import BaseSettings, SettingsConfigDict

from src.core.app_factory import create_app
from src.core.config import Config
from src.core.module import Module
from tests.core._support import AuthStubModule


class _StubConfig(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="STUB_", extra="ignore")
    value: int = 42


class _StubModule(Module):
    name = "stub"
    config_cls = _StubConfig

    def configure(self, app: FastAPI, config: Config) -> None:
        @app.get("/api/stub/ping")
        async def _ping():
            return {"ok": True}


class _StubModuleNoConfig(Module):
    name = "stub"

    def configure(self, app: FastAPI, config: Config) -> None:
        @app.get("/api/stub/ping")
        async def _ping():
            return {"ok": True}


@pytest.fixture
def config() -> Config:
    return Config()


@pytest.mark.pure
def test_create_app_returns_fastapi(config: Config):
    app = create_app(modules=[AuthStubModule()], config=config)
    assert isinstance(app, FastAPI)


@pytest.mark.pure
def test_create_app_stores_config(config: Config):
    app = create_app(modules=[AuthStubModule()], config=config)
    assert app.state.config is config


@pytest.mark.pure
def test_module_configs_instantiated(config: Config):
    app = create_app(modules=[AuthStubModule(), _StubModule()], config=config)
    assert "stub" in app.state.module_configs
    assert isinstance(app.state.module_configs["stub"], _StubConfig)
    assert app.state.module_configs["stub"].value == 42


@pytest.mark.pure
def test_module_without_config_not_added(config: Config):
    app = create_app(modules=[AuthStubModule(), _StubModuleNoConfig()], config=config)
    assert "stub" not in app.state.module_configs


@pytest.mark.pure
def test_configure_is_called(config: Config):
    app = create_app(modules=[AuthStubModule(), _StubModule()], config=config)
    paths = [r.path for r in app.routes if hasattr(r, "path")]
    assert "/api/stub/ping" in paths


@pytest.mark.pure
def test_server_disabled_skips_core_zone():
    app = create_app(modules=[], config=Config(server_enabled=False))
    paths = [r.path for r in app.routes if hasattr(r, "path")]
    assert not any(p.startswith("/internal/core") for p in paths)


@pytest.mark.pure
def test_server_enabled_mounts_core_zone():
    app = create_app(modules=[AuthStubModule()], config=Config(server_enabled=True))
    paths = [r.path for r in app.routes if hasattr(r, "path")]
    assert any(p.startswith("/internal/core") for p in paths)


@pytest.mark.pure
async def test_health_public_available_when_api_enabled():
    """The public /internal/health is reachable without auth when the API is on."""
    from httpx import ASGITransport, AsyncClient

    app = create_app(modules=[AuthStubModule()], config=Config(server_enabled=True))
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        r = await c.get("/internal/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


@pytest.mark.pure
async def test_health_absent_when_api_disabled():
    """With the API off there is no zone ⇒ /internal/health is unavailable (404)."""
    from httpx import ASGITransport, AsyncClient

    app = create_app(modules=[], config=Config(server_enabled=False))
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        r = await c.get("/internal/health")
    assert r.status_code == 404


@pytest.mark.pure
async def test_debug_delay_slows_internal_requests():
    """SERVER_DEBUG_DELAY_MS>0 mounts a zone delay — the request waits ≈ the given time."""
    import time

    from httpx import ASGITransport, AsyncClient

    app = create_app(
        modules=[AuthStubModule()],
        config=Config(server_enabled=True, server_debug_delay_ms=200),
    )
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        start = time.perf_counter()
        r = await c.get("/internal/health")
        elapsed = time.perf_counter() - start
    assert r.status_code == 200
    assert elapsed >= 0.18  # margin below 0.2s for scheduler jitter


@pytest.mark.pure
async def test_debug_delay_zero_is_fast():
    """SERVER_DEBUG_DELAY_MS=0 (default) — the dependency is not mounted, no delay."""
    import time

    from httpx import ASGITransport, AsyncClient

    app = create_app(modules=[AuthStubModule()], config=Config(server_enabled=True))
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        start = time.perf_counter()
        r = await c.get("/internal/health")
        elapsed = time.perf_counter() - start
    assert r.status_code == 200
    assert elapsed < 0.1


@pytest.mark.pure
def test_swagger_and_openapi_disabled():
    """Swagger/OpenAPI are off in both modes — an internal API, we don't publish the schema."""
    for enabled in (True, False):
        app = create_app(modules=[AuthStubModule()], config=Config(server_enabled=enabled))
        assert app.docs_url is None
        assert app.openapi_url is None
        paths = [r.path for r in app.routes if hasattr(r, "path")]
        assert not any(p in ("/docs", "/openapi.json") for p in paths)


class _BadGuardModule(Module):
    name = "bad"

    def configure(self, app: FastAPI, config: Config) -> None:
        from src.core.router import guard

        @app.get("/api/bad/x")
        @guard("nope")
        async def _x():
            return {}


@pytest.mark.pure
def test_unknown_guard_kind_raises_on_build():
    with pytest.raises(RuntimeError, match="not registered"):
        create_app(
            modules=[AuthStubModule(), _BadGuardModule()],
            config=Config(server_enabled=True),
        )


@pytest.mark.pure
def test_server_disabled_still_registers_tasks():
    """Scheduler-only mode: configure() (and task registration) always runs."""
    app = create_app(modules=[_StubModule()], config=Config(server_enabled=False))
    paths = [r.path for r in app.routes if hasattr(r, "path")]
    # the stub's route is added in configure directly (not in a zone) — it exists even without
    # the API zone; the point: configure was called (tasks would register the same way).
    assert "/api/stub/ping" in paths


@pytest.mark.db
async def test_lifespan_initializes_db(config: Config):
    from src.core.database import get_engine

    app = create_app(modules=[AuthStubModule()], config=config)
    async with app.router.lifespan_context(app):
        assert get_engine() is not None
    assert get_engine() is None


@pytest.mark.db
async def test_module_router_reachable_via_lifespan(config: Config):
    from httpx import ASGITransport, AsyncClient

    app = create_app(modules=[AuthStubModule(), _StubModule()], config=config)
    transport = ASGITransport(app=app)
    async with app.router.lifespan_context(app):
        async with AsyncClient(transport=transport, base_url="http://test") as c:
            r = await c.get("/api/stub/ping")
            assert r.status_code == 200
            assert r.json() == {"ok": True}


# ── mcp zone (mounted FastMCP servers) ──────────────────────────────────
# Modules declare MCP servers (mcp_servers: code → constructor) + supply a
# token resolver (mcp_token_resolver). The core builds McpServerContext,
# mounts each server as an ASGI sub-app under /mcp/<code> and composes
# their lifespans. See src/core/mcp/, src/core/router/mcp.py.


def _stub_mcp_server(ctx):
    """Minimal stub MCP server via the core factory make_mcp_server."""
    from src.core.mcp import make_mcp_server

    mcp = make_mcp_server("stub", "stub server", ctx)

    @mcp.tool()
    async def ping() -> dict:
        return {"ok": True}

    return mcp


async def _stub_resolver(token: str, scope: str):
    """Stub resolver (like core_users.resolve_token): only 'good' is valid."""
    return SimpleNamespace(id=1, group="admin") if token == "good" else None


class _McpStubModule(Module):
    """Declares the MCP server 'stub' + supplies a token resolver."""

    name = "mcp_stub"
    mcp_servers = {"stub": _stub_mcp_server}
    mcp_token_resolver = staticmethod(_stub_resolver)


class _McpDupModule(Module):
    """Declares the same code 'stub' (no resolver) — to test a code collision."""

    name = "mcp_dup"
    mcp_servers = {"stub": _stub_mcp_server}


@pytest.mark.pure
def test_build_guard_registry_has_builtins_and_module_guards():
    """build_guard_registry (router/mounting): built-in kinds + merged Module.guards."""
    from src.core.router.mounting import build_guard_registry

    registry = build_guard_registry([AuthStubModule()])
    assert registry.has("allow_all")
    assert registry.has("deny_all")
    assert registry.has("auth")  # from AuthStubModule.guards
    assert registry.has("ability")
    assert not registry.has("token")  # not registered yet


def _mount_paths(app) -> list[str]:
    """Paths of mounted sub-apps (Mount) — they have .path."""
    return [r.path for r in app.routes if hasattr(r, "path")]


@pytest.mark.pure
def test_mcp_not_mounted_without_provider():
    """No module with mcp_servers ⇒ nothing is mounted under /mcp."""
    app = create_app(modules=[AuthStubModule()], config=Config(server_enabled=True))
    assert not any(p.startswith("/mcp") for p in _mount_paths(app))


@pytest.mark.pure
def test_mcp_mounted_when_module_provides_server():
    """A module provided mcp_servers ⇒ the server is mounted as the sub-app /mcp/<code>."""
    app = create_app(
        modules=[AuthStubModule(), _McpStubModule()],
        config=Config(server_enabled=True),
    )
    assert "/mcp/stub" in _mount_paths(app)


@pytest.mark.pure
def test_mcp_skipped_when_api_disabled():
    """SERVER_ENABLED=false ⇒ MCP servers are not mounted even when mcp_servers exist."""
    app = create_app(
        modules=[AuthStubModule(), _McpStubModule()],
        config=Config(server_enabled=False),
    )
    assert not any(p.startswith("/mcp") for p in _mount_paths(app))


@pytest.mark.pure
def test_mcp_duplicate_code_raises():
    """Two modules with the same code ⇒ RuntimeError at build time (a loud refusal)."""
    with pytest.raises(RuntimeError, match="duplicate mcp server code"):
        create_app(
            modules=[AuthStubModule(), _McpStubModule(), _McpDupModule()],
            config=Config(server_enabled=True),
        )


@pytest.mark.pure
def test_mcp_missing_resolver_raises():
    """mcp_servers exist but nobody supplied mcp_token_resolver ⇒ RuntimeError."""
    with pytest.raises(RuntimeError, match="mcp_token_resolver"):
        create_app(
            modules=[AuthStubModule(), _McpDupModule()],
            config=Config(server_enabled=True),
        )


@pytest.mark.db
async def test_mcp_lifespan_composes(config: Config):
    """A mounted MCP server: its lifespan is composed (the session manager is up)."""
    app = create_app(
        modules=[AuthStubModule(), _McpStubModule()],
        config=config,
    )
    assert "/mcp/stub" in _mount_paths(app)
    async with app.router.lifespan_context(app):
        pass  # enter/exit without errors ⇒ http_app().lifespan joined the stack


@pytest.mark.db
async def test_mcp_endpoint_served_at_code_root_not_double_mcp(config: Config):
    """The server endpoint is exactly /mcp/<code>, NOT /mcp/<code>/mcp.

    Regression: the sub-app listens on streamable_http_path="/mcp" by default; without path="/"
    in http_app() the real endpoint drifts to /mcp/stub/mcp (307→404), and /mcp/stub/
    returns 404 — exactly what the client probe was hitting ("Connection Failed").
    """
    from httpx import ASGITransport, AsyncClient

    app = create_app(modules=[AuthStubModule(), _McpStubModule()], config=config)
    body = {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}}
    headers = {"Accept": "application/json, text/event-stream"}
    transport = ASGITransport(app=app)
    async with app.router.lifespan_context(app):
        async with AsyncClient(transport=transport, base_url="http://test") as c:
            # At the code root the endpoint is ALIVE and gates on auth (401), not 404.
            at_root = await c.post("/mcp/stub/", json=body, headers=headers)
            assert at_root.status_code == 401
            # The old erroneous doubled path no longer exists.
            doubled = await c.post("/mcp/stub/mcp", json=body, headers=headers)
            assert doubled.status_code == 404
