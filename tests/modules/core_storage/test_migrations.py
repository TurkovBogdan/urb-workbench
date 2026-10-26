"""Migrations ``csm_*``: both tables come, go and come back, on both providers.

The schema itself is compared with the models elsewhere (``tests/core/test_migrations.py``); here
is what that comparison cannot see — that the branch rolls back to nothing on its own without
touching the neighbouring chains, that the dedup key and the ``RESTRICT`` hold in the real schema,
and that the owner table carries the name columns in the revision's order with their ``''`` defaults.
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

_BASE = "csm_001_files@base"
_FILE = (
    "INSERT INTO core_storage_file (code, store, sha256, type, size, mime, extension, created_at) "
    "VALUES (:code, 'public', :sha, 'text', 1, 'text/plain', '.txt', CURRENT_TIMESTAMP)"
)
_OWNER = (
    "INSERT INTO core_storage_file_owner (file_code, owner_type, owner_id, created_at) "
    "VALUES (:code, 'task', '7DB4F6E0DE', CURRENT_TIMESTAMP)"
)
_NAMED_OWNER = (
    "INSERT INTO core_storage_file_owner "
    "(file_code, owner_type, owner_id, original_filename, original_extension, created_at) "
    "VALUES (:code, 'note', 'BD98065ED2', 'report.final', '.PDF', CURRENT_TIMESTAMP)"
)
_OWNER_COLUMNS = [
    "file_code",
    "owner_type",
    "owner_id",
    "owner_key",
    "original_filename",
    "original_extension",
    "deleted_at",
    "created_at",
]


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


async def _owner_columns(engine) -> list[dict]:
    async with engine.connect() as connection:
        return await connection.run_sync(lambda c: inspect(c).get_columns("core_storage_file_owner"))


async def _cycle(engine) -> None:
    from src.apps.app.modules import build_modules

    runner = AlembicRunner(modules=build_modules())
    await _migrate(engine, runner, "heads")
    assert {"core_storage_file", "core_storage_file_owner"} <= await _tables(engine)

    columns = {column["name"]: column for column in await _owner_columns(engine)}
    assert list(columns) == _OWNER_COLUMNS
    assert [columns[name]["type"].length for name in ("original_filename", "original_extension")] == [255, 16]
    assert not columns["original_filename"]["nullable"] and not columns["original_extension"]["nullable"]

    await _rows(engine, _FILE, code="AAAAAAAAAA", sha="a" * 64)
    await _rows(engine, _OWNER, code="AAAAAAAAAA")
    await _rows(engine, _NAMED_OWNER, code="AAAAAAAAAA")
    assert await _rows(
        engine,
        "SELECT owner_type, owner_key, original_filename, original_extension "
        "FROM core_storage_file_owner ORDER BY owner_type",
    ) == [("note", "", "report.final", ".PDF"), ("task", "", "", "")]
    with pytest.raises(IntegrityError):
        await _rows(engine, _FILE, code="BBBBBBBBBB", sha="a" * 64)
    with pytest.raises(IntegrityError):
        await _rows(engine, "DELETE FROM core_storage_file WHERE code = 'AAAAAAAAAA'")

    await _migrate(engine, runner, _BASE, down=True)
    after_down = await _tables(engine)
    assert not {"core_storage_file", "core_storage_file_owner"} & after_down
    assert {"workspaces", "tasks", "notes"} <= after_down

    await _migrate(engine, runner, "heads")
    assert await _rows(engine, "SELECT count(*) FROM core_storage_file") == [(0,)]


@pytest.mark.db
async def test_sqlite_creates_drops_and_recreates_the_storage_tables(tmp_path):
    config = Config(db_provider="sqlite", db_path=str(tmp_path / "app.sqlite3"))
    engine = create_async_engine(config.database_url, **config.engine_kwargs)
    configure_sqlite(engine, config)
    try:
        await _cycle(engine)
    finally:
        await engine.dispose()


@pytest.mark.heavy
async def test_postgres_creates_drops_and_recreates_the_storage_tables(config: Config):
    engine = create_async_engine(config.database_url)
    try:
        await _cycle(engine)
    finally:
        await engine.dispose()
