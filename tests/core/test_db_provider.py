"""DB_PROVIDER: choosing the DB provider (postgres|sqlite) + the sqlite schema from the models."""

from __future__ import annotations

import pytest
from sqlalchemy import insert, select
from sqlalchemy.ext.asyncio import create_async_engine

from src.core.config import Config
from src.core.database.runtime import create_all
from src.core.models.module_state import CoreModuleState
from src.core.utils.date import utc_now


@pytest.mark.pure
def test_postgres_url_and_pool_kwargs():
    """Credentials are set here rather than pulled from the installation's ``.env``.

    Postgres requires them, and without explicit fields the test caught not the provider's
    behaviour but how the machine running it was set up: on a SQLite install it failed validation.
    """
    cfg = Config(
        _env_file=None,
        db_provider="postgres",
        db_host="db.example", db_name="appdb", db_user="appuser", db_password="secret",
    )

    assert cfg.database_url.startswith("postgresql+asyncpg://")
    assert "pool_size" in cfg.engine_kwargs and "connect_args" in cfg.engine_kwargs


@pytest.mark.pure
def test_sqlite_url_and_minimal_kwargs():
    cfg = Config(db_provider="sqlite", db_path="/tmp/x.sqlite3")
    assert cfg.database_url == "sqlite+aiosqlite:////tmp/x.sqlite3"
    # SQLite does not tune the pool — only a per-connection busy timeout.
    assert cfg.engine_kwargs == {"connect_args": {"timeout": cfg.db_connect_timeout}}


@pytest.mark.pure
def test_sqlite_default_path_in_runtime_root():
    cfg = Config(db_provider="sqlite", db_path="")
    assert cfg.database_url.endswith("app.sqlite3")


@pytest.mark.pure
def test_sqlite_in_memory_url_and_static_pool():
    from sqlalchemy.pool import StaticPool

    cfg = Config(db_provider="sqlite", db_path=":memory:")
    assert cfg.sqlite_in_memory is True
    assert cfg.database_url == "sqlite+aiosqlite://"
    # An in-memory DB lives in one connection — a shared StaticPool is mandatory.
    assert cfg.engine_kwargs["poolclass"] is StaticPool
    assert cfg.engine_kwargs["connect_args"]["check_same_thread"] is False


@pytest.mark.pure
async def test_sqlite_in_memory_create_all_roundtrip():
    cfg = Config(db_provider="sqlite", db_path=":memory:")
    engine = create_async_engine(cfg.database_url, **cfg.engine_kwargs)
    try:
        await create_all(engine)
        now = utc_now()
        async with engine.begin() as conn:
            await conn.execute(
                insert(CoreModuleState).values(
                    module="m", code="c", value={"x": 1},
                    created_at=now, updated_at=now,
                )
            )
        # The same in-memory DB is visible to a new session — thanks to StaticPool.
        async with engine.connect() as conn:
            value = (
                await conn.execute(
                    select(CoreModuleState.value).where(CoreModuleState.code == "c")
                )
            ).scalar_one()
        assert value == {"x": 1}
    finally:
        await engine.dispose()


@pytest.mark.pure
def test_postgres_requires_connection_fields():
    with pytest.raises(ValueError, match="DB_PROVIDER=postgres requires"):
        Config(db_provider="postgres", db_host="", db_name="", db_user="", db_password="")


@pytest.mark.pure
def test_sqlite_does_not_require_postgres_fields():
    cfg = Config(db_provider="sqlite", db_host="", db_name="", db_user="", db_password="")
    assert cfg.db_provider == "sqlite"


@pytest.mark.pure
async def test_sqlite_create_all_and_json_timestamp_roundtrip(tmp_path):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path}/app.sqlite3")
    try:
        await create_all(engine)
        now = utc_now()
        async with engine.begin() as conn:
            await conn.execute(
                insert(CoreModuleState).values(
                    module="m", code="c", value={"cursor": 42, "items": [1, 2]},
                    created_at=now, updated_at=now,
                )
            )
        async with engine.connect() as conn:
            value = (
                await conn.execute(
                    select(CoreModuleState.value).where(CoreModuleState.code == "c")
                )
            ).scalar_one()
        assert value == {"cursor": 42, "items": [1, 2]}
    finally:
        await engine.dispose()
