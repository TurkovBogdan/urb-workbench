"""The ``cxm_*`` chain comes, goes and comes back, on both providers, and builds the model schema.

The table-level comparison with the models over the whole tree is ``tests/core/test_migrations.py``;
here is what it does not look at — that the chain rolls back to nothing without touching its
neighbours, that the partial unique indexes come out partial (a full index would refuse a segment a
deleted row once had), that the mount default is true on the real column, and that a body at its
full width fits on PostgreSQL, where ``VARCHAR(n)`` is enforced.

The unique indexes are compared with the models' — name, columns and condition — because the
schema-level suites build from the models and would stay green on a migration that drifted.
"""

from __future__ import annotations

import re

import pytest
from alembic import command
from sqlalchemy import inspect, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import create_async_engine

from src.core.config import Config
from src.core.database.migrations import AlembicRunner
from src.core.database.sqlite import WRITE_EXECUTION_OPTIONS, configure_sqlite, foreign_keys_disabled
from src.modules.codex.models import Codex, CodexNote

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


def _condition(clause) -> str:
    """A partial index condition as one comparable string; PostgreSQL reflects it parenthesised."""
    if clause is None:
        return ""
    return re.sub(r"\s+", " ", re.sub(r"[()]", "", str(clause))).strip().lower()


async def _unique_indexes(engine, table: str) -> dict[str, tuple[list[str], str]]:
    async with engine.connect() as connection:
        found = await connection.run_sync(lambda c: inspect(c).get_indexes(table))
    return {
        index["name"]: (index["column_names"], _condition(_reflected_where(index)))
        for index in found
        if index["unique"]
    }


def _reflected_where(index: dict):
    options = index.get("dialect_options", {})
    return options["sqlite_where"] if "sqlite_where" in options else options.get("postgresql_where")


def _model_unique_indexes(model) -> dict[str, tuple[list[str], str]]:
    return {
        index.name: (
            [column.name for column in index.columns],
            _condition(index.dialect_options["sqlite"]["where"]),
        )
        for index in model.__table__.indexes
        if index.unique
    }


async def _codex(
    engine, code: str, segment: str, *, deleted: bool = False, body: str = ""
) -> None:
    await _sql(
        engine,
        "INSERT INTO codex (code, segment, title, body, deleted_at, created_at, updated_at) "
        f"VALUES (:code, :segment, :segment, :body, {_NOW if deleted else 'NULL'}, {_NOW}, {_NOW})",
        code=code,
        segment=segment,
        body=body,
    )


async def _note(
    engine, code: str, segment: str, *, parent: str | None = None, deleted: bool = False
) -> None:
    await _sql(
        engine,
        "INSERT INTO codex_note "
        "(code, codex_code, parent_code, segment, title, deleted_at, created_at, updated_at) "
        f"VALUES (:code, 'C000000001', :parent, :segment, :segment, "
        f"{_NOW if deleted else 'NULL'}, {_NOW}, {_NOW})",
        code=code,
        parent=parent,
        segment=segment,
    )


async def _cycle(engine) -> None:
    from src.apps.app.modules import build_modules

    runner = AlembicRunner(modules=build_modules())
    await _migrate(engine, runner, "heads")
    assert _TABLES <= await _tables(engine)
    codex_indexes = await _unique_indexes(engine, "codex")
    note_indexes = await _unique_indexes(engine, "codex_note")
    assert set(codex_indexes) == {"ux_codex_segment"}
    assert set(note_indexes) == {"ux_codex_note_parent_segment", "ux_codex_note_top_segment"}
    assert codex_indexes == _model_unique_indexes(Codex)
    assert note_indexes == _model_unique_indexes(CodexNote)

    await _codex(engine, "C0000000DD", "python", deleted=True)
    await _codex(engine, "C000000001", "python", body="ж" * 65536)
    assert await _sql(engine, "SELECT length(body), sort FROM codex WHERE code = 'C000000001'") == [
        (65536, 500)
    ]
    with pytest.raises(IntegrityError):
        await _codex(engine, "C000000002", "python")

    await _note(engine, "N000000001", "test")
    with pytest.raises(IntegrityError):
        await _note(engine, "N000000002", "test")
    # The top-level index holds the top level only: a child may repeat a top-level segment.
    await _note(engine, "N000000003", "test", parent="N000000001")
    with pytest.raises(IntegrityError):
        await _note(engine, "N000000004", "test", parent="N000000001")
    # A deleted note frees its segment on either level.
    await _note(engine, "N000000005", "old", deleted=True)
    await _note(engine, "N000000006", "old")
    await _note(engine, "N000000007", "gone", parent="N000000001", deleted=True)
    await _note(engine, "N000000008", "gone", parent="N000000001")

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
    # cxm_004: a row written without the flag is a live mount.
    assert await _sql(engine, "SELECT enabled FROM codex_mount") in ([(1,)], [(True,)])

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
