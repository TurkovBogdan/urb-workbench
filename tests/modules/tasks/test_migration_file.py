"""Migration ``tsm_011``: ``tasks_file`` comes, goes and comes back, its constraints and cascades hold.

The table joins three chains — ``tasks``, ``notes`` and ``core_storage`` — so what can go quietly
wrong is the order between them, the one-place check and the cascades. All of it is exercised on
the migrated schema, not read from its definition; the shape is compared with the model's, since
the db suites build from the models and would stay green on a revision that drifted.
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
from src.modules.tasks.models import TasksFile

_BEFORE = "tsm_010_note"
_AFTER = "tsm_011_file"
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
        if "tasks_file" not in inspector.get_table_names():
            return {}
        return {
            "columns": [column["name"] for column in inspector.get_columns("tasks_file")],
            "pk": sorted(inspector.get_pk_constraint("tasks_file")["constrained_columns"]),
            "foreign_keys": sorted(
                (fk["name"], fk["referred_table"], (fk.get("options") or {}).get("ondelete"))
                for fk in inspector.get_foreign_keys("tasks_file")
            ),
            "indexes": sorted(
                (index["name"], tuple(index["column_names"]))
                for index in inspector.get_indexes("tasks_file")
            ),
            "checks": sorted(check["name"] for check in inspector.get_check_constraints("tasks_file")),
        }

    async with engine.connect() as connection:
        return await connection.run_sync(read)


def _model_shape() -> dict:
    table = TasksFile.__table__
    return {
        "columns": [column.name for column in table.columns],
        "pk": sorted(column.name for column in table.primary_key.columns),
        "foreign_keys": sorted(
            (fk.name, fk.column.table.name, fk.ondelete) for fk in table.foreign_keys
        ),
        "indexes": sorted((index.name, tuple(c.name for c in index.columns)) for index in table.indexes),
        "checks": ["ck_tasks_file_one_place"],
    }


async def _seed(engine) -> None:
    await _rows(
        engine,
        "INSERT INTO workspaces (code, title, description, icon, color, sort, created_at, "
        f"updated_at) VALUES ('AAAAAAAAAA', 'W', '', '', '', 500, {_NOW}, {_NOW})",
    )
    await _rows(
        engine,
        "INSERT INTO tasks (code, workspace_code, title, type, created_at, updated_at) "
        f"VALUES ('BBBBBBBBBB', 'AAAAAAAAAA', 'T', 'extended', {_NOW}, {_NOW})",
    )
    await _rows(
        engine,
        "INSERT INTO tasks_stage (code, task_code, number, title, created_at, updated_at) "
        f"VALUES ('CCCCCCCCCC', 'BBBBBBBBBB', 1, 'S', {_NOW}, {_NOW})",
    )
    await _rows(
        engine,
        "INSERT INTO notes (code, title, description, body, created_at, updated_at) "
        f"VALUES ('DDDDDDDDDD', 'N', '', '', {_NOW}, {_NOW})",
    )
    for code in ("F000000001", "F000000002", "F000000003"):
        await _rows(
            engine,
            "INSERT INTO core_storage_file (code, store, sha256, type, size, mime, extension, "
            f"created_at) VALUES ('{code}', 'public', '{code * 6}{code[:4]}', 'text', 1, "
            f"'text/plain', '.txt', {_NOW})",
        )
    for file_code, note, stage in (
        ("F000000001", "NULL", "'CCCCCCCCCC'"),
        ("F000000002", "'DDDDDDDDDD'", "NULL"),
        ("F000000003", "NULL", "NULL"),
    ):
        await _rows(
            engine,
            "INSERT INTO tasks_file (task_code, file_code, note_code, stage_code, created_at, "
            f"updated_at) VALUES ('BBBBBBBBBB', '{file_code}', {note}, {stage}, {_NOW}, {_NOW})",
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
        engine, "SELECT title, description, sort FROM tasks_file WHERE file_code = 'F000000003'"
    ) == [("", "", 500)]
    with pytest.raises(IntegrityError):
        await _rows(
            engine,
            "UPDATE tasks_file SET note_code = 'DDDDDDDDDD', stage_code = 'CCCCCCCCCC' "
            "WHERE file_code = 'F000000003'",
        )
    with pytest.raises(IntegrityError):
        await _rows(
            engine,
            "INSERT INTO tasks_file (task_code, file_code, created_at, updated_at) "
            f"VALUES ('BBBBBBBBBB', 'F000000003', {_NOW}, {_NOW})",
        )
    # Each holder takes its rows: the stage, the note, then the file itself.
    await _rows(engine, "DELETE FROM tasks_stage WHERE code = 'CCCCCCCCCC'")
    await _rows(engine, "DELETE FROM notes WHERE code = 'DDDDDDDDDD'")
    assert await _rows(engine, "SELECT file_code FROM tasks_file") == [("F000000003",)]
    await _rows(engine, "DELETE FROM core_storage_file WHERE code = 'F000000003'")
    assert await _rows(engine, "SELECT count(*) FROM tasks_file") == [(0,)]


@pytest.mark.db
async def test_sqlite_creates_drops_and_recreates_tasks_file_with_its_constraints(tmp_path):
    config = Config(db_provider="sqlite", db_path=str(tmp_path / "app.sqlite3"))
    engine = create_async_engine(config.database_url, **config.engine_kwargs)
    configure_sqlite(engine, config)
    try:
        await _cycle(engine)
    finally:
        await engine.dispose()


@pytest.mark.heavy
async def test_postgres_creates_drops_and_recreates_tasks_file_with_its_constraints(config: Config):
    engine = create_async_engine(config.database_url)
    try:
        await _cycle(engine)
    finally:
        await engine.dispose()
