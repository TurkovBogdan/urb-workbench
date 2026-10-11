"""The ``cxm_*`` chain comes, goes and comes back, on both providers, and builds the model schema.

The table-level comparison with the models over the whole tree is ``tests/core/test_migrations.py``;
here is what it does not look at — that the chain rolls back to nothing without touching its
neighbours, that the partial unique indexes come out partial (a full index would refuse a slug a
deleted row once had), that the mount default is true on the real column, and that a body at its
full width fits on PostgreSQL, where ``VARCHAR(n)`` is enforced.
"""

from __future__ import annotations

import pytest
from alembic import command
from sqlalchemy import inspect, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import create_async_engine

from src.core.config import Config
from src.core.database.migrations import AlembicRunner
from src.core.database.sqlite import WRITE_EXECUTION_OPTIONS, configure_sqlite, foreign_keys_disabled

_BASE = "cxm_001_codex@base"
_TABLES = {"codex", "codex_note", "codex_mount"}
_NOW = "CURRENT_TIMESTAMP"


async def _migrate(engine, runner: AlembicRunner, target: str, *, down: bool = False) -> None:
    def run(connection):
        connection.execution_options(**WRITE_EXECUTION_OPTIONS)
        with foreign_keys_disabled(connection):
            cfg = runner._build_config(connection)
            (command.downgrade if down else command.upgrade)(cfg, target)

    async with engine.connect() as connection:
        await connection.run_sync(run)


async def _sql(engine, sql: str, **params) -> list:
    async with engine.connect() as connection:
        await connection.execution_options(**WRITE_EXECUTION_OPTIONS)
        async with connection.begin():
            result = await connection.execute(text(sql), params)
            return [tuple(row) for row in result.fetchall()] if result.returns_rows else []


async def _tables(engine) -> set[str]:
    async with engine.connect() as connection:
        return set(await connection.run_sync(lambda c: inspect(c).get_table_names()))


async def _codex(engine, code: str, slug: str, *, deleted: bool = False, body: str = "") -> None:
    await _sql(
        engine,
        "INSERT INTO codex (code, slug, title, body, deleted_at, created_at, updated_at) "
        f"VALUES (:code, :slug, :slug, :body, {_NOW if deleted else 'NULL'}, {_NOW}, {_NOW})",
        code=code,
        slug=slug,
        body=body,
    )


async def _top_note(engine, code: str, slug: str) -> None:
    await _sql(
        engine,
        "INSERT INTO codex_note (code, codex_code, slug, title, created_at, updated_at) "
        f"VALUES (:code, 'C000000001', :slug, :slug, {_NOW}, {_NOW})",
        code=code,
        slug=slug,
    )


async def _cycle(engine) -> None:
    from src.apps.app.modules import build_modules

    runner = AlembicRunner(modules=build_modules())
    await _migrate(engine, runner, "heads")
    assert _TABLES <= await _tables(engine)

    await _codex(engine, "C0000000DD", "python", deleted=True)
    await _codex(engine, "C000000001", "python", body="ж" * 65536)
    assert await _sql(engine, "SELECT length(body), sort FROM codex WHERE code = 'C000000001'") == [
        (65536, 500)
    ]
    with pytest.raises(IntegrityError):
        await _codex(engine, "C000000002", "python")

    await _top_note(engine, "N000000001", "test")
    with pytest.raises(IntegrityError):
        await _top_note(engine, "N000000002", "test")

    await _sql(
        engine,
        "INSERT INTO workspaces (code, title, created_at, updated_at) "
        f"VALUES ('W000000001', 'Работа', {_NOW}, {_NOW})",
    )
    await _sql(
        engine,
        "INSERT INTO codex_mount (codex_code, workspace_code, created_at) "
        f"VALUES ('C000000001', 'W000000001', {_NOW})",
    )
    assert await _sql(engine, "SELECT agent_can_edit FROM codex_mount") in ([(1,)], [(True,)])

    await _migrate(engine, runner, _BASE, down=True)
    after_down = await _tables(engine)
    assert not _TABLES & after_down
    assert {"workspaces", "notes", "tasks"} <= after_down

    await _migrate(engine, runner, "heads")
    assert await _sql(engine, "SELECT count(*) FROM codex") == [(0,)]


@pytest.mark.db
async def test_sqlite_creates_drops_and_recreates_the_codex_chain(tmp_path):
    config = Config(db_provider="sqlite", db_path=str(tmp_path / "app.sqlite3"))
    engine = create_async_engine(config.database_url, **config.engine_kwargs)
    configure_sqlite(engine, config)
    try:
        await _cycle(engine)
    finally:
        await engine.dispose()


@pytest.mark.heavy
async def test_postgres_creates_drops_and_recreates_the_codex_chain(config: Config):
    engine = create_async_engine(config.database_url)
    try:
        await _cycle(engine)
    finally:
        await engine.dispose()
