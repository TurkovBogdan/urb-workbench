"""Migration ``csu_001_request``: the upload requests table comes, goes and comes back, on both
providers.

The schema itself is compared with the models elsewhere (``tests/core/test_migrations.py``); here
is what that comparison cannot see — that the branch rolls back to nothing on its own without
touching the neighbouring chains, that the columns come in the revision's order with their widths,
that the token hash is the key and the payload keeps its JSON.
"""

from __future__ import annotations

import json

import pytest
from alembic import command
from sqlalchemy import inspect, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import create_async_engine

from src.core.config import Config
from src.core.database.migrations import AlembicRunner
from src.core.database.sqlite import WRITE_EXECUTION_OPTIONS, configure_sqlite, foreign_keys_disabled

_BASE = "csu_001_request@base"
_TABLE = "core_storage_upload_request"
_REQUEST = (
    "INSERT INTO core_storage_upload_request "
    "(token_hash, holder, workspace_code, payload, expires_at, created_at) "
    "VALUES (:hash, 'TASK@7DB4F6E0DE', 'E62302907D', :payload, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"
)
_COLUMNS = [
    "token_hash",
    "holder",
    "workspace_code",
    "filename",
    "payload",
    "claimed_at",
    "expires_at",
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


async def _columns(engine) -> list[dict]:
    async with engine.connect() as connection:
        return await connection.run_sync(lambda c: inspect(c).get_columns(_TABLE))


async def _indexes(engine) -> set[str]:
    async with engine.connect() as connection:
        return {i["name"] for i in await connection.run_sync(lambda c: inspect(c).get_indexes(_TABLE))}


async def _cycle(engine) -> None:
    from src.apps.app.modules import build_modules

    runner = AlembicRunner(modules=build_modules())
    await _migrate(engine, runner, "heads")
    assert _TABLE in await _tables(engine)

    columns = {column["name"]: column for column in await _columns(engine)}
    assert list(columns) == _COLUMNS
    assert [columns[name]["type"].length for name in ("token_hash", "holder", "workspace_code", "filename")] == [
        64, 64, 64, 272
    ]
    assert columns["claimed_at"]["nullable"] and not columns["expires_at"]["nullable"]
    assert "ix_core_storage_upload_request_expires_at" in await _indexes(engine)

    payload = json.dumps({"title": "Экран", "description": "вход"}, ensure_ascii=False)
    await _rows(engine, _REQUEST, hash="a" * 64, payload=payload)
    [(filename, stored)] = await _rows(engine, f"SELECT filename, payload FROM {_TABLE}")
    assert filename == ""
    assert (json.loads(stored) if isinstance(stored, str) else stored) == {
        "title": "Экран",
        "description": "вход",
    }
    with pytest.raises(IntegrityError):
        await _rows(engine, _REQUEST, hash="a" * 64, payload=payload)

    await _migrate(engine, runner, _BASE, down=True)
    after_down = await _tables(engine)
    assert _TABLE not in after_down
    assert {"workspaces", "tasks", "core_storage_file"} <= after_down

    await _migrate(engine, runner, "heads")
    assert await _rows(engine, f"SELECT count(*) FROM {_TABLE}") == [(0,)]


@pytest.mark.db
async def test_sqlite_creates_drops_and_recreates_the_requests_table(tmp_path):
    config = Config(db_provider="sqlite", db_path=str(tmp_path / "app.sqlite3"))
    engine = create_async_engine(config.database_url, **config.engine_kwargs)
    configure_sqlite(engine, config)
    try:
        await _cycle(engine)
    finally:
        await engine.dispose()


@pytest.mark.heavy
async def test_postgres_creates_drops_and_recreates_the_requests_table(config: Config):
    engine = create_async_engine(config.database_url)
    try:
        await _cycle(engine)
    finally:
        await engine.dispose()
