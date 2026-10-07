"""``workspace`` test fixtures: a fresh in-memory DB with the module schema and an HTTP client.

``db`` builds the schema from the ORM models (``create_all``) on a new ``:memory:`` database —
migrations are not applied here, they belong to the heavy tier.

``app``/``client`` mount the module router on a bare ``FastAPI`` rather than via ``create_app``:
the tests are about the module's routes, and dragging the application lifecycle in for them is
pointless. The one thing that has to be added by hand is ``register_exception_handlers``: without
it ``ApiError`` flies past the handler, and instead of a 404 with a ``{"error": …}`` body the test
would get an exception (see ``docs/platform/api-zones.md``).

``no_counters`` clears the counter registry: the full application would bring in other modules'
counters (``tasks`` registers its own in ``configure()``), and the module must answer on its own
too — when no module at all is mounted above it.
"""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from src.core.api import register_exception_handlers
from src.core.config import Config
from src.core.database import close_database, init_database
from src.modules.workspace.api import router
from src.modules.workspace.stats import reset_counters


@pytest.fixture(autouse=True)
def no_counters():
    """Counters are cleared on entry and exit: the registry is process-global, so leftovers leak."""
    reset_counters()
    yield
    reset_counters()


@pytest.fixture
async def db(config: Config):
    engine = await init_database(config)
    from src.core.database.runtime import Base
    import src.modules.workspace.models  # noqa: F401 — registers the workspace table

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    try:
        yield
    finally:
        await close_database()


@pytest.fixture
async def app(config: Config):
    engine = await init_database(config)
    from src.core.database.runtime import Base
    import src.modules.workspace.models  # noqa: F401 — registers the workspace table

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    fastapi_app = FastAPI()
    register_exception_handlers(fastapi_app)
    # The prefix mirrors the production one (``WorkspaceModule.internal_router_prefix``).
    fastapi_app.include_router(router, prefix="/internal/workspace")
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
