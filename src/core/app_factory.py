"""Application factory: builds the FastAPI app from a set of modules.

A minimal factory — DB, settings, module registration. The makeup of the HTTP zone
``internal`` (including the public ``/health``) is in ``src/core/router/internal.py``;
web specifics (CORS, static files) are in ``apps/<name>/server.py``.
"""

from __future__ import annotations

from collections.abc import Sequence
from contextlib import AbstractAsyncContextManager, AsyncExitStack, asynccontextmanager

from fastapi import FastAPI
from sqlalchemy.ext.asyncio import AsyncEngine

from src.core import scheduler
from src.core.settings.bootstrap import (
    load_initial_stores,
    register_settings_schemas,
)
from src.core.settings.registry import get_registry as get_settings_registry
from src.core.api import register_exception_handlers
from src.core.config import Config
from src.core.database import close_database, create_all, init_database
from src.core.database.migrations import AlembicRunner
from src.core.loggers import get_logger
from src.core.module import Module
from src.core.router.degraded import (
    degraded_pending,
    mark_degraded,
    mount_degraded_gate,
)
from src.core.router.internal import HEALTH_PATH
from src.core.router.mounting import mount_router_zones
from src.core.scheduler.registry import get_registry
from src.core.tasks import register as register_core_tasks

_LOG = get_logger()


async def _apply_chain_or_degrade(
    app: FastAPI, engine: AsyncEngine, modules: Sequence[Module]
) -> None:
    """Startup does NOT migrate a database that already has a schema — it degrades.

    The exception is an empty database: a fresh install has nothing to lose and nothing to
    protect, so the chain is applied silently. The marker disappears with the very first
    upgrade, so this branch is never reached twice. Any other lag → a stub instead of data
    (see router/degraded.py).
    """
    runner = AlembicRunner(modules=modules)
    status = await runner.status(engine)
    pending = [revision.revision for revision in status.pending]
    no_revision_recorded = not status.current_heads
    if no_revision_recorded:
        await _bootstrap_or_degrade(app, runner, engine, pending)
        return
    if status.up_to_date:
        return
    mark_degraded(app, pending)
    _LOG.error(
        "lifespan: the DB schema is behind the code — serving a stub instead of data; "
        "not applied: %s (apply them by updating the installation, not by starting the app)",
        ", ".join(pending),
    )


async def _bootstrap_or_degrade(
    app: FastAPI, runner: AlembicRunner, engine: AsyncEngine, pending: list[str]
) -> None:
    """With no row in ``alembic_version`` the database counts as empty — but it may not be.

    A database once built through ``create_all`` already carries tables, and the very first
    revision fails on ``table already exists``. An exception here would bring down the whole
    lifespan — exactly the blind failure the stub mode exists to prevent — so such a database
    degrades, and the cause goes to the log.
    """
    try:
        await runner.upgrade_head(engine)
    except Exception:  # noqa: BLE001
        mark_degraded(app, pending)
        _LOG.exception(
            "lifespan: the database has no alembic_version, yet the chain would not apply — "
            "serving a stub; not applied: %s (a schema exists without a migration history — "
            "the database must be brought to a revision by hand)",
            ", ".join(pending),
        )
        return
    _LOG.info("lifespan: empty database — applied the whole chain (%d revisions)", len(pending))


def create_app(modules: Sequence[Module], config: Config) -> FastAPI:
    """Build the FastAPI app from an explicit list of modules."""

    # Lifespans of the mounted MCP servers: filled in the build phase below
    # (mount_router_zones) and composed here through an AsyncExitStack. Late-binding
    # closure: it reads the name at startup, after the build phase is over.
    mcp_lifespans: list[AbstractAsyncContextManager[None]] = []

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        _LOG.info("lifespan: startup, modules=%s", [m.name for m in modules])
        engine = await init_database(config)
        if config.sqlite_in_memory:
            # Only in-memory SQLite (tests, StaticPool on a single connection) builds the
            # schema from the models — it has no migration history and lives for one run.
            # File databases (dev sqlite and postgres) always go through Alembic.
            await create_all(engine)
            _LOG.info("lifespan: in-memory sqlite — schema built from models (create_all)")
        else:
            await _apply_chain_or_degrade(app, engine, modules)

        # A degraded start does not touch the DB at all: both load_initial_stores and on_startup
        # read/write against the lagging schema, and an exception from there would bring down
        # the whole lifespan — exactly the failure the stub mode exists to prevent.
        serves_data = degraded_pending(app) is None
        if serves_data:
            await load_initial_stores(modules)
            for m in modules:
                try:
                    await m.on_startup(app)
                except Exception as exc:  # noqa: BLE001
                    _LOG.exception("lifespan: %s.on_startup raised %s", m.name, exc)
        # Start the MCP servers' session managers (the fork initialises them in the lifespan
        # of its http_app); they close automatically on leaving the stack.
        async with AsyncExitStack() as mcp_stack:
            for cm in mcp_lifespans:
                await mcp_stack.enter_async_context(cm)
            if serves_data:
                await scheduler.start(config)
            else:
                _LOG.error(
                    "lifespan: scheduler not started — the DB schema is behind the code; a pure "
                    "worker has no HTTP surface, so there is nowhere else for it to refuse"
                )
            try:
                yield
            finally:
                _LOG.info("lifespan: shutdown")
                await scheduler.stop()
                for m in reversed(list(modules)):
                    try:
                        await m.shutdown(app)
                    except Exception as exc:  # noqa: BLE001
                        _LOG.exception(
                            "lifespan: %s.shutdown raised %s", m.name, exc
                        )
                await close_database()

    # Swagger/OpenAPI are DISABLED: the API is internal, the schema is not published (FastAPI
    # would enable /docs + /openapi.json by default). The SERVER_ENABLED gate is below.
    app = FastAPI(
        title="Uroboros.Workbench",
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
        lifespan=lifespan,
    )
    app.state.config = config
    # Filled in the lifespan when the migration chain is behind (see _apply_chain_or_degrade).
    app.state.degraded = None
    app.state.module_configs = {
        m.name: m.config_cls() for m in modules if m.config_cls is not None
    }
    get_registry().clear()
    get_settings_registry().clear()
    register_core_tasks()
    register_exception_handlers(app)

    # ── build phase ─────────────────────────────────────────────────────
    # configure() ALWAYS runs: it registers scheduler tasks (needed in "scheduler only"
    # mode too). Mounting the HTTP surface is separate, behind a flag.
    register_settings_schemas(modules)
    for m in modules:
        m.configure(app, config)

    # ── HTTP surface: the SERVER_ENABLED gate (visible right here) ──────
    # ON/OFF for the whole surface is this condition; which zones get mounted and under
    # what conditions is in mount_router_zones (src/core/router/mounting.py).
    if config.server_enabled:
        mcp_lifespans = mount_router_zones(app, modules, config)
        # Strictly AFTER mounting the zones: add_middleware inserts at position 0, so the
        # one added last is the outermost, and only this way does the gate intercept the
        # request before the SPA middleware (attached by mount_spa inside the call above).
        mount_degraded_gate(app, health_path=HEALTH_PATH)
    else:
        _LOG.info(
            "create_app: SERVER_ENABLED=false — the core API surface is not "
            "mounted (worker-only mode)"
        )

    return app


__all__ = ["create_app"]
