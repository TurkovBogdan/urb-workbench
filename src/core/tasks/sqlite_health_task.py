"""Здоровье файловой базы SQLite: размер журнала и две проверки целостности.

У движка почти нет громких отказов. Голодание чекпойнта не логируется и не
возвращает ошибку — растущий файл-спутник рядом с небольшой базой единственный
его признак. А ``integrity_check`` не смотрит на внешние ключи вовсе, поэтому
проверок две, а не одна.
"""

from __future__ import annotations

from pathlib import Path

from sqlalchemy import text

from src.core.config import get_config
from src.core.database import get_engine
from src.core.scheduler import CoreTaskBase, TaskContext

_WAL_SHARE_TO_WARN = 0.25


class SqliteHealthTask(CoreTaskBase):
    """Раз в час: размер журнала относительно базы + целостность страниц и ссылок."""

    MODULE = "core"
    CODE = "sqlite_health"
    NAME = "SQLite health"
    # Английский запасной текст: интерфейс показывает перевод из словаря по (MODULE, CODE).
    DESCRIPTION = (
        "Hourly: size of the WAL companion file relative to the database (checkpoint "
        "starvation shows no other sign), quick_check and foreign_key_check."
    )
    SCHEDULE = "17 * * * *"
    TTL = 300

    @staticmethod
    async def handle(ctx: TaskContext) -> None:
        database_file = get_config().sqlite_file
        if database_file is None or not database_file.exists():
            await ctx.info("provider is not a file-based sqlite — nothing to check")
            return

        database_bytes = database_file.stat().st_size
        wal_bytes = _companion_size(database_file)
        await ctx.info(
            "database %.1f MB, journal %.1f MB",
            database_bytes / 1024 / 1024,
            wal_bytes / 1024 / 1024,
        )
        if database_bytes and wal_bytes > database_bytes * _WAL_SHARE_TO_WARN:
            await ctx.warn(
                "journal grew to %.0f%% of the database size — the checkpoint doesn't finish its work",
                wal_bytes / database_bytes * 100,
            )

        engine = get_engine()
        assert engine is not None, "init_database() not called"
        async with engine.connect() as connection:
            pages = (await connection.execute(text("PRAGMA quick_check"))).scalar()
            violations = (await connection.execute(text("PRAGMA foreign_key_check"))).all()
        if pages != "ok":
            await ctx.error("quick_check: %s", pages)
        if violations:
            await ctx.error("foreign key violations: %d", len(violations))


def _companion_size(database_file: Path) -> int:
    companion = database_file.with_name(f"{database_file.name}-wal")
    return companion.stat().st_size if companion.exists() else 0


__all__ = ["SqliteHealthTask"]
