"""Migration ``tsm_009``: the task plan survives the rename, both ways, on both providers.

The db tests build the schema with ``create_all`` and never run this revision over a database
that already holds a plan. Here it runs for real — up, down and up again, over a task with a
plan and the rows hanging off it:

- on SQLite the revision rebuilds ``tasks``, and dropping the old table would cascade to its
  children unless the runner turns foreign keys off around it — the stage, the journal entry and
  the tree edge must still be there;
- on PostgreSQL batch mode alters in place, and it refused the column placement SQLite accepted —
  the revision failed there outright until placement was made SQLite-only.
"""

from __future__ import annotations

import pytest
from alembic import command
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from src.core.config import Config
from src.core.database.migrations import AlembicRunner
from src.core.database.sqlite import WRITE_EXECUTION_OPTIONS, configure_sqlite, foreign_keys_disabled

_BEFORE = "tsm_008_brief_lists_len"
_PLAN = "## Подход\n" + "п" * 8000 + "\n\nМеняю: tariff.py"
_CHILDREN = ("tasks_link", "tasks_stage", "tasks_note")


async def _migrate(engine, runner: AlembicRunner, target: str, *, down: bool = False) -> None:
    """The runner's own way: outside a transaction, foreign keys off for the rebuild."""

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


async def _columns(engine) -> list[str]:
    def read(connection):
        from sqlalchemy import inspect

        return [column["name"] for column in inspect(connection).get_columns("tasks")]

    async with engine.connect() as connection:
        return await connection.run_sync(read)


async def _children(engine) -> list[int]:
    return [(await _rows(engine, f"SELECT count(*) FROM {table}"))[0][0] for table in _CHILDREN]


async def _seed_at_tsm_008(engine) -> None:
    now = "CURRENT_TIMESTAMP"
    await _rows(
        engine,
        "INSERT INTO workspaces (code, title, description, icon, color, sort, created_at, "
        f"updated_at) VALUES ('AAAAAAAAAA', 'W', '', '', '', 500, {now}, {now})",
    )
    await _rows(
        engine,
        "INSERT INTO tasks (code, workspace_code, title, type, body, created_at, updated_at) "
        f"VALUES ('BBBBBBBBBB', 'AAAAAAAAAA', 'T', 'extended', :plan, {now}, {now})",
        plan=_PLAN,
    )
    await _rows(
        engine,
        f"INSERT INTO tasks_link (task_code, parent_code, sort, updated_at) "
        f"VALUES ('BBBBBBBBBB', NULL, 500, {now})",
    )
    await _rows(
        engine,
        "INSERT INTO tasks_stage (code, task_code, number, status, title, description, body, "
        f"evidence, created_at, updated_at) VALUES ('CCCCCCCCCC', 'BBBBBBBBBB', 1, 'planned', "
        f"'S', '', 'шаг', '', {now}, {now})",
    )
    await _rows(
        engine,
        "INSERT INTO tasks_note (code, task_code, type, title, body, resolution, created_at) "
        f"VALUES ('DDDDDDDDDD', 'BBBBBBBBBB', 'fact', 'N', 'запись', '', {now})",
    )


async def _cycle(engine) -> None:
    from src.apps.app.modules import build_modules

    runner = AlembicRunner(modules=build_modules())
    # Every other branch at head, the tasks branch one step back: the database as an
    # installation has it right before this revision lands.
    await _migrate(engine, runner, "heads")
    await _migrate(engine, runner, _BEFORE, down=True)
    assert "body" in await _columns(engine)
    await _seed_at_tsm_008(engine)
    children = await _children(engine)
    assert children == [1, 1, 1]

    await _migrate(engine, runner, "heads")
    columns = await _columns(engine)
    assert "body" not in columns
    assert {"plan", "progress", "result"} <= set(columns)
    assert await _rows(engine, "SELECT plan, progress, result FROM tasks") == [(_PLAN, "", "")]
    assert await _children(engine) == children

    await _migrate(engine, runner, _BEFORE, down=True)
    columns = await _columns(engine)
    assert "body" in columns and not {"plan", "progress", "result"} & set(columns)
    assert await _rows(engine, "SELECT body FROM tasks") == [(_PLAN,)]
    assert await _children(engine) == children

    await _migrate(engine, runner, "heads")
    assert await _rows(engine, "SELECT plan FROM tasks") == [(_PLAN,)]
    assert await _children(engine) == children


@pytest.mark.db
async def test_sqlite_carries_the_plan_and_the_children_through_up_down_up(tmp_path):
    config = Config(db_provider="sqlite", db_path=str(tmp_path / "app.sqlite3"))
    engine = create_async_engine(config.database_url, **config.engine_kwargs)
    configure_sqlite(engine, config)
    try:
        await _cycle(engine)
        columns = await _columns(engine)
        # SQLite rebuilds the table and can place a column: the work fields follow the brief.
        assert columns[columns.index("criteria") + 1 : columns.index("criteria") + 4] == [
            "plan",
            "progress",
            "result",
        ]
    finally:
        await engine.dispose()


@pytest.mark.heavy
async def test_postgres_carries_the_plan_and_the_children_through_up_down_up(config: Config):
    engine = create_async_engine(config.database_url)
    try:
        await _cycle(engine)
    finally:
        await engine.dispose()


@pytest.mark.heavy
async def test_postgres_columns_hold_their_width(config: Config):
    """The database itself refuses an over-long result — the cap is not only in the code."""
    from src.apps.app.modules import build_modules

    engine = create_async_engine(config.database_url)
    try:
        await _migrate(engine, AlembicRunner(modules=build_modules()), "heads")
        widths = dict(
            await _rows(
                engine,
                "SELECT column_name, character_maximum_length FROM information_schema.columns "
                "WHERE table_name = 'tasks' AND column_name IN ('plan', 'progress', 'result')",
            )
        )
        assert widths == {"plan": 8192, "progress": 16384, "result": 2048}
    finally:
        await engine.dispose()
