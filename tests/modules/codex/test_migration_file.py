"""Migration ``cxm_005``: ``codex_file`` comes, goes and comes back, and both cascades hold.

The table joins the ``codex`` and ``core_storage`` chains. Its shape is compared with the model's
(the db suites build from the models and would stay green on a revision that drifted), and the
cascades are exercised on the migrated schema.
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
from src.modules.codex.models import CodexFile

_BEFORE = "cxm_004_codex_mount_enabled"
_AFTER = "cxm_005_file"
_NOW = "CURRENT_TIMESTAMP"


async def _migrate(engine, runner: AlembicRunner, target: str, *, down: bool = False) -> None:
    def run(connection):
        connection.execution_options(**WRITE_EXECUTION_OPTIONS)
        with foreign_keys_disabled(connection):
            cfg = runner._build_config(connection)
            (command.downgrade if down else command.upgrade)(cfg, target)

    async with engine.connect() as connection:
        await connection.run_sync(run)


async def _rows(engine, sql: str) -> list:
    async with engine.connect() as connection:
        await connection.execution_options(**WRITE_EXECUTION_OPTIONS)
        async with connection.begin():
            result = await connection.execute(text(sql))
            return [tuple(row) for row in result.fetchall()] if result.returns_rows else []


async def _shape(engine) -> dict:
    def read(connection):
        inspector = inspect(connection)
        if "codex_file" not in inspector.get_table_names():
            return {}
        return {
            "columns": [column["name"] for column in inspector.get_columns("codex_file")],
            "pk": sorted(inspector.get_pk_constraint("codex_file")["constrained_columns"]),
            "foreign_keys": sorted(
                (fk["name"], fk["referred_table"], (fk.get("options") or {}).get("ondelete"))
                for fk in inspector.get_foreign_keys("codex_file")
            ),
            "indexes": sorted(
                (index["name"], tuple(index["column_names"]))
                for index in inspector.get_indexes("codex_file")
            ),
        }

    async with engine.connect() as connection:
        return await connection.run_sync(read)


def _model_shape() -> dict:
    table = CodexFile.__table__
    return {
        "columns": [column.name for column in table.columns],
        "pk": sorted(column.name for column in table.primary_key.columns),
        "foreign_keys": sorted(
            (fk.name, fk.column.table.name, fk.ondelete) for fk in table.foreign_keys
        ),
        "indexes": sorted((index.name, tuple(c.name for c in index.columns)) for index in table.indexes),
    }


async def _seed(engine) -> None:
    await _rows(
        engine,
        "INSERT INTO codex (code, segment, title, created_at, updated_at) "
        f"VALUES ('C000000001', 'python', 'Python', {_NOW}, {_NOW})",
    )
    for note in ("N000000001", "N000000002"):
        await _rows(
            engine,
            "INSERT INTO codex_note (code, codex_code, segment, title, created_at, updated_at) "
            f"VALUES ('{note}', 'C000000001', '{note.lower()}', 'N', {_NOW}, {_NOW})",
        )
    for code in ("F000000001", "F000000002"):
        await _rows(
            engine,
            "INSERT INTO core_storage_file (code, store, sha256, type, size, mime, extension, "
            f"created_at) VALUES ('{code}', 'public', '{code * 6}{code[:4]}', 'text', 1, "
            f"'text/plain', '.txt', {_NOW})",
        )
    for note, file_code in (("N000000001", "F000000001"), ("N000000002", "F000000002")):
        await _rows(
            engine,
            "INSERT INTO codex_file (note_code, file_code, created_at, updated_at) "
            f"VALUES ('{note}', '{file_code}', {_NOW}, {_NOW})",
        )


async def _cycle(engine) -> None:
    from src.apps.app.modules import build_modules

    runner = AlembicRunner(modules=build_modules())
    await _migrate(engine, runner, "heads")
    assert await _shape(engine) == _model_shape()

    await _migrate(engine, runner, _BEFORE, down=True)
    assert await _shape(engine) == {}
    await _migrate(engine, runner, _AFTER)
    assert await _shape(engine) == _model_shape()

    await _seed(engine)
    assert await _rows(
        engine, "SELECT title, description, sort FROM codex_file WHERE note_code = 'N000000001'"
    ) == [("", "", 500)]
    with pytest.raises(IntegrityError):
        await _rows(
            engine,
            "INSERT INTO codex_file (note_code, file_code, created_at, updated_at) "
            f"VALUES ('C000000001', 'F000000001', {_NOW}, {_NOW})",
        )
    await _rows(engine, "DELETE FROM codex_note WHERE code = 'N000000001'")
    assert await _rows(engine, "SELECT file_code FROM codex_file") == [("F000000002",)]
    await _rows(engine, "DELETE FROM core_storage_file WHERE code = 'F000000002'")
    assert await _rows(engine, "SELECT count(*) FROM codex_file") == [(0,)]


@pytest.mark.db
async def test_sqlite_creates_drops_and_recreates_codex_file_with_both_cascades(tmp_path):
    config = Config(db_provider="sqlite", db_path=str(tmp_path / "app.sqlite3"))
    engine = create_async_engine(config.database_url, **config.engine_kwargs)
    configure_sqlite(engine, config)
    try:
        await _cycle(engine)
    finally:
        await engine.dispose()


@pytest.mark.heavy
async def test_postgres_creates_drops_and_recreates_codex_file_with_both_cascades(config: Config):
    engine = create_async_engine(config.database_url)
    try:
        await _cycle(engine)
    finally:
        await engine.dispose()
