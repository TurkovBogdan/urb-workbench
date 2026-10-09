"""Migration ``ntm_001``: the ``notes`` table comes, goes and comes back, on both providers.

The schema itself is compared with the models elsewhere (``tests/core/test_migrations.py``); here
is what that comparison cannot see — that the branch rolls back to nothing on its own, without
touching the neighbouring chains, and that a body at its full width fits on PostgreSQL, where
``VARCHAR(n)`` is enforced.
"""

from __future__ import annotations

import pytest
from alembic import command
from sqlalchemy import inspect, text
from sqlalchemy.ext.asyncio import create_async_engine

from src.core.config import Config
from src.core.database.migrations import AlembicRunner
from src.core.database.sqlite import WRITE_EXECUTION_OPTIONS, configure_sqlite, foreign_keys_disabled

_BASE = "ntm_001_notes@base"


async def _migrate(engine, runner: AlembicRunner, target: str, *, down: bool = False) -> None:
    def run(connection):
        connection.execution_options(**WRITE_EXECUTION_OPTIONS)
        with foreign_keys_disabled(connection):
            cfg = runner._build_config(connection)
            (command.downgrade if down else command.upgrade)(cfg, target)

    async with engine.connect() as connection:
        await connection.run_sync(run)


async def _rows(engine, sql: str, **params) -> list:
    async with engine.connect() as connection:
        await connection.execution_options(**WRITE_EXECUTION_OPTIONS)
        async with connection.begin():
            result = await connection.execute(text(sql), params)
            return [tuple(row) for row in result.fetchall()] if result.returns_rows else []


async def _tables(engine) -> set[str]:
    async with engine.connect() as connection:
        return set(await connection.run_sync(lambda c: inspect(c).get_table_names()))


async def _cycle(engine) -> None:
    from src.apps.app.modules import build_modules

    runner = AlembicRunner(modules=build_modules())
    await _migrate(engine, runner, "heads")
    assert "notes" in await _tables(engine)

    await _rows(
        engine,
        "INSERT INTO notes (code, title, description, body, created_at, updated_at) "
        "VALUES ('AAAAAAAAAA', 'Схема', '', :body, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)",
        body="ж" * 65536,
    )
    assert await _rows(engine, "SELECT length(body), description FROM notes") == [(65536, "")]

    await _migrate(engine, runner, _BASE, down=True)
    after_down = await _tables(engine)
    assert "notes" not in after_down
    assert {"workspaces", "tasks", "tasks_journal"} <= after_down

    await _migrate(engine, runner, "heads")
    assert await _rows(engine, "SELECT count(*) FROM notes") == [(0,)]


@pytest.mark.db
async def test_sqlite_creates_drops_and_recreates_notes(tmp_path):
    config = Config(db_provider="sqlite", db_path=str(tmp_path / "app.sqlite3"))
    engine = create_async_engine(config.database_url, **config.engine_kwargs)
    configure_sqlite(engine, config)
    try:
        await _cycle(engine)
    finally:
        await engine.dispose()


@pytest.mark.heavy
async def test_postgres_creates_drops_and_recreates_notes(config: Config):
    engine = create_async_engine(config.database_url)
    try:
        await _cycle(engine)
    finally:
        await engine.dispose()
