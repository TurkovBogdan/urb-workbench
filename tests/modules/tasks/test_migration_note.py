"""Migration ``tsm_010``: ``tasks_note`` comes, goes and comes back, and both cascades hold.

The table links two chains — ``tasks`` and ``notes`` — so what can go quietly wrong is the
order between them and the cascades: a hard-deleted task must take its links and leave the
documents, a hard-deleted document must take its link. Both are exercised on the migrated
schema, not read from its definition.
"""

from __future__ import annotations

import pytest
from alembic import command
from sqlalchemy import inspect, text
from sqlalchemy.ext.asyncio import create_async_engine

from src.core.config import Config
from src.core.database.migrations import AlembicRunner
from src.core.database.sqlite import WRITE_EXECUTION_OPTIONS, configure_sqlite, foreign_keys_disabled

_BEFORE = "tsm_009_journal"
_AFTER = "tsm_010_note"


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
        if "tasks_note" not in inspector.get_table_names():
            return {}
        return {
            "pk": inspector.get_pk_constraint("tasks_note")["constrained_columns"],
            "foreign_keys": sorted(
                (fk["name"], fk["referred_table"], (fk.get("options") or {}).get("ondelete"))
                for fk in inspector.get_foreign_keys("tasks_note")
            ),
            "indexes": sorted(index["name"] for index in inspector.get_indexes("tasks_note")),
        }

    async with engine.connect() as connection:
        return await connection.run_sync(read)


_EXPECTED = {
    "pk": ["note_code"],
    "foreign_keys": [
        ("fk_tasks_note_note_code", "notes", "CASCADE"),
        ("fk_tasks_note_task_code", "tasks", "CASCADE"),
    ],
    "indexes": ["ix_tasks_note_task_sort"],
}


async def _seed(engine) -> None:
    now = "CURRENT_TIMESTAMP"
    await _rows(
        engine,
        "INSERT INTO workspaces (code, title, description, icon, color, sort, created_at, "
        f"updated_at) VALUES ('AAAAAAAAAA', 'W', '', '', '', 500, {now}, {now})",
    )
    await _rows(
        engine,
        "INSERT INTO tasks (code, workspace_code, title, type, created_at, updated_at) "
        f"VALUES ('BBBBBBBBBB', 'AAAAAAAAAA', 'T', 'simple', {now}, {now})",
    )
    for note in ("CCCCCCCCCC", "DDDDDDDDDD"):
        await _rows(
            engine,
            "INSERT INTO notes (code, title, description, body, created_at, updated_at) "
            f"VALUES ('{note}', 'N', '', '', {now}, {now})",
        )
        await _rows(
            engine,
            "INSERT INTO tasks_note (note_code, task_code, sort, created_at) "
            f"VALUES ('{note}', 'BBBBBBBBBB', 500, {now})",
        )


async def _cycle(engine) -> None:
    from src.apps.app.modules import build_modules

    runner = AlembicRunner(modules=build_modules())
    await _migrate(engine, runner, "heads")
    assert await _shape(engine) == _EXPECTED

    await _migrate(engine, runner, _BEFORE, down=True)
    assert await _shape(engine) == {}
    await _migrate(engine, runner, _AFTER)
    assert await _shape(engine) == _EXPECTED

    await _seed(engine)
    # A hard-deleted document takes its link; the other note stays linked.
    await _rows(engine, "DELETE FROM notes WHERE code = 'CCCCCCCCCC'")
    assert await _rows(engine, "SELECT note_code FROM tasks_note") == [("DDDDDDDDDD",)]
    # A hard-deleted task takes its links and leaves the documents.
    await _rows(engine, "DELETE FROM tasks WHERE code = 'BBBBBBBBBB'")
    assert await _rows(engine, "SELECT count(*) FROM tasks_note") == [(0,)]
    assert await _rows(engine, "SELECT code FROM notes") == [("DDDDDDDDDD",)]


@pytest.mark.db
async def test_sqlite_creates_drops_and_recreates_tasks_note_with_both_cascades(tmp_path):
    config = Config(db_provider="sqlite", db_path=str(tmp_path / "app.sqlite3"))
    engine = create_async_engine(config.database_url, **config.engine_kwargs)
    configure_sqlite(engine, config)
    try:
        await _cycle(engine)
    finally:
        await engine.dispose()


@pytest.mark.heavy
async def test_postgres_creates_drops_and_recreates_tasks_note_with_both_cascades(config: Config):
    engine = create_async_engine(config.database_url)
    try:
        await _cycle(engine)
    finally:
        await engine.dispose()
