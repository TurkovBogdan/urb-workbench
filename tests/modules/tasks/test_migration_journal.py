"""Migration ``tsm_010``: the journal is renamed, its rows and its cascade survive, both ways.

Only names change — the table, the check, both foreign keys, both indexes. What can go wrong is
quiet: SQLite cannot rename a constraint, so the table is rebuilt, and a foreign key re-declared
without ``ON DELETE CASCADE`` would leave a deleted task's journal behind with no error anywhere.
So the cascade is exercised on the renamed table, not just read from its definition.
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

_BEFORE = "tsm_009_task_work_fields"
_AFTER = "tsm_010_journal"


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


async def _shape(engine, table: str) -> dict:
    """The names a table carries: its own, the check, the foreign keys with their action, indexes."""

    def read(connection):
        inspector = inspect(connection)
        if table not in inspector.get_table_names():
            return {}
        return {
            "checks": sorted(c["name"] for c in inspector.get_check_constraints(table)),
            "foreign_keys": sorted(
                (fk["name"], fk["referred_table"], (fk.get("options") or {}).get("ondelete"))
                for fk in inspector.get_foreign_keys(table)
            ),
            "indexes": sorted(index["name"] for index in inspector.get_indexes(table)),
        }

    async with engine.connect() as connection:
        return await connection.run_sync(read)


def _expected(table: str) -> dict:
    return {
        "checks": [f"ck_{table}_type"],
        "foreign_keys": [
            (f"fk_{table}_stage_code", "tasks_stage", "CASCADE"),
            (f"fk_{table}_task_code", "tasks", "CASCADE"),
        ],
        "indexes": [f"ix_{table}_stage", f"ix_{table}_task_created"],
    }


async def _seed(engine) -> None:
    now = "CURRENT_TIMESTAMP"
    await _rows(
        engine,
        "INSERT INTO workspaces (code, title, description, icon, color, sort, created_at, "
        f"updated_at) VALUES ('AAAAAAAAAA', 'W', '', '', '', 500, {now}, {now})",
    )
    for code in ("BBBBBBBBBB", "CCCCCCCCCC"):
        await _rows(
            engine,
            "INSERT INTO tasks (code, workspace_code, title, type, created_at, updated_at) "
            f"VALUES ('{code}', 'AAAAAAAAAA', 'T', 'extended', {now}, {now})",
        )
        await _rows(
            engine,
            "INSERT INTO tasks_note (code, task_code, type, title, body, resolution, created_at) "
            f"VALUES ('N{code[1:]}', '{code}', 'decision', 'Решение', 'подробности', '', {now})",
        )


async def _cycle(engine) -> None:
    from src.apps.app.modules import build_modules

    runner = AlembicRunner(modules=build_modules())
    await _migrate(engine, runner, "heads")
    await _migrate(engine, runner, _BEFORE, down=True)
    await _seed(engine)
    before = await _rows(engine, "SELECT * FROM tasks_note ORDER BY code")
    assert len(before) == 2

    await _migrate(engine, runner, _AFTER)
    assert await _shape(engine, "tasks_note") == {}
    assert await _shape(engine, "tasks_journal") == _expected("tasks_journal")
    assert await _rows(engine, "SELECT * FROM tasks_journal ORDER BY code") == before

    await _migrate(engine, runner, _BEFORE, down=True)
    assert await _shape(engine, "tasks_journal") == {}
    assert await _shape(engine, "tasks_note") == _expected("tasks_note")
    assert await _rows(engine, "SELECT * FROM tasks_note ORDER BY code") == before

    await _migrate(engine, runner, _AFTER)
    assert await _rows(engine, "SELECT * FROM tasks_journal ORDER BY code") == before

    # The check still runs on the rebuilt table, not just carries its name.
    with pytest.raises(IntegrityError):
        await _rows(
            engine,
            "INSERT INTO tasks_journal (code, task_code, type, title, body, resolution, created_at) "
            "VALUES ('XXXXXXXXXX', 'BBBBBBBBBB', 'bogus', 'T', '', '', CURRENT_TIMESTAMP)",
        )

    # The cascade still runs on the renamed table: a deleted task takes its journal along.
    await _rows(engine, "DELETE FROM tasks WHERE code = 'BBBBBBBBBB'")
    assert await _rows(engine, "SELECT task_code FROM tasks_journal") == [("CCCCCCCCCC",)]


@pytest.mark.db
async def test_sqlite_renames_the_journal_and_keeps_rows_and_cascade(tmp_path):
    config = Config(db_provider="sqlite", db_path=str(tmp_path / "app.sqlite3"))
    engine = create_async_engine(config.database_url, **config.engine_kwargs)
    configure_sqlite(engine, config)
    try:
        await _cycle(engine)
    finally:
        await engine.dispose()


@pytest.mark.heavy
async def test_postgres_renames_the_journal_and_keeps_rows_and_cascade(config: Config):
    engine = create_async_engine(config.database_url)
    try:
        await _cycle(engine)
    finally:
        await engine.dispose()
