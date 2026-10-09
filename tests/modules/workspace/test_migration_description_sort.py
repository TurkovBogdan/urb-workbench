"""Migration ``wkm_003``: the description clips to 128 and the position arrives, both ways.

The db tests build the schema with ``create_all`` and never run this revision over a database
that already holds a workspace. Here it runs for real — up, down and up again, over a workspace
with a description longer than the new width and a task hanging off it:

- the description is clipped before the column narrows, and the tail stays lost on the way down;
- on SQLite the revision rebuilds ``workspaces``, the parent of every ``workspace_code`` with
  ``ON DELETE CASCADE`` — the task must still be there after each rebuild;
- the list index follows the position: ``ix_workspaces_deleted_sort`` up, the title one down.
"""

from __future__ import annotations

import pytest
from alembic import command
from sqlalchemy import inspect, text
from sqlalchemy.ext.asyncio import create_async_engine

from src.core.config import Config
from src.core.database.migrations import AlembicRunner
from src.core.database.sqlite import WRITE_EXECUTION_OPTIONS, configure_sqlite, foreign_keys_disabled

_BEFORE = "wkm_002_workspaces_list_index"
_AFTER = "wkm_003_description_sort"
_DESCRIPTION = "Пространство " + "д" * 300
_NEW_WIDTH = 128


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


async def _shape(engine) -> tuple[list[str], list[str]]:
    """The columns of ``workspaces`` in table order, and its index names."""

    def read(connection):
        inspector = inspect(connection)
        columns = [column["name"] for column in inspector.get_columns("workspaces")]
        indexes = sorted(index["name"] for index in inspector.get_indexes("workspaces"))
        return columns, indexes

    async with engine.connect() as connection:
        return await connection.run_sync(read)


async def _seed_at_wkm_002(engine) -> None:
    now = "CURRENT_TIMESTAMP"
    await _rows(
        engine,
        "INSERT INTO workspaces (code, title, description, icon, color, created_at, updated_at) "
        f"VALUES ('AAAAAAAAAA', 'W', :description, '', '', {now}, {now})",
        description=_DESCRIPTION,
    )
    await _rows(
        engine,
        "INSERT INTO tasks (code, workspace_code, title, type, created_at, updated_at) "
        f"VALUES ('BBBBBBBBBB', 'AAAAAAAAAA', 'T', 'extended', {now}, {now})",
    )


async def _cycle(engine) -> list[str]:
    from src.apps.app.modules import build_modules

    runner = AlembicRunner(modules=build_modules())
    # Every other branch at head, the workspace branch one step back: the database as an
    # installation has it right before this revision lands.
    await _migrate(engine, runner, "heads")
    await _migrate(engine, runner, _BEFORE, down=True)
    columns, indexes = await _shape(engine)
    assert "sort" not in columns
    assert "ix_workspaces_deleted_title" in indexes
    await _seed_at_wkm_002(engine)

    await _migrate(engine, runner, _AFTER)
    columns, indexes = await _shape(engine)
    assert "ix_workspaces_deleted_sort" in indexes
    assert "ix_workspaces_deleted_title" not in indexes
    assert await _rows(engine, "SELECT description, sort FROM workspaces") == [
        (_DESCRIPTION[:_NEW_WIDTH], 500)
    ]
    assert await _rows(engine, "SELECT code FROM tasks") == [("BBBBBBBBBB",)]
    after_up = columns

    await _migrate(engine, runner, _BEFORE, down=True)
    columns, indexes = await _shape(engine)
    assert "sort" not in columns
    assert "ix_workspaces_deleted_title" in indexes
    assert "ix_workspaces_deleted_sort" not in indexes
    assert await _rows(engine, "SELECT description FROM workspaces") == [
        (_DESCRIPTION[:_NEW_WIDTH],)
    ]
    assert await _rows(engine, "SELECT code FROM tasks") == [("BBBBBBBBBB",)]

    await _migrate(engine, runner, _AFTER)
    assert await _rows(engine, "SELECT sort FROM workspaces") == [(500,)]
    assert await _rows(engine, "SELECT code FROM tasks") == [("BBBBBBBBBB",)]
    return after_up


@pytest.mark.db
async def test_sqlite_clips_places_the_position_and_keeps_the_children(tmp_path):
    config = Config(db_provider="sqlite", db_path=str(tmp_path / "app.sqlite3"))
    engine = create_async_engine(config.database_url, **config.engine_kwargs)
    configure_sqlite(engine, config)
    try:
        columns = await _cycle(engine)
        # SQLite rebuilds the table and can place a column: the position follows the model.
        assert columns[columns.index("icon") + 1] == "sort"
    finally:
        await engine.dispose()


@pytest.mark.heavy
async def test_postgres_clips_adds_the_position_and_keeps_the_children(config: Config):
    engine = create_async_engine(config.database_url)
    try:
        await _cycle(engine)
        widths = dict(
            await _rows(
                engine,
                "SELECT column_name, character_maximum_length FROM information_schema.columns "
                "WHERE table_name = 'workspaces' AND column_name = 'description'",
            )
        )
        assert widths == {"description": _NEW_WIDTH}
    finally:
        await engine.dispose()
