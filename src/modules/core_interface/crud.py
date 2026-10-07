"""CRUD for the ``core_interface_settings`` table. Each function opens its own scope.

Only reading and batch writing are exposed (over HTTP). Deletion has no endpoint: a human
resets a setting **to its default**, and that the store removes a row in doing so is its own
internal business. Hence the three remaining functions: ``delete_many`` is called by the reset
handler, ``prune_unknown`` is the cleanup at module startup, ``delete_all`` is kept for
migrations.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from sqlalchemy import delete as sa_delete, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.database import session_scope, write_scope
from src.core.utils.date import utc_now
from src.modules.core_interface.models import InterfaceSetting


def _insert_for(session: AsyncSession):
    dialect = session.bind.dialect.name if session.bind else "postgresql"
    if dialect == "sqlite":
        return sqlite_insert
    return pg_insert


async def list_all() -> dict[str, Any]:
    """The whole map of deviations: rows number in the dozens, so it is always read in full."""
    async with session_scope() as s:
        rows = (await s.execute(select(InterfaceSetting))).scalars().all()
        return {row.key: row.value for row in rows}


async def upsert_many(values: Mapping[str, Any]) -> None:
    """A batch in one write transaction: whatever accumulated during the debounce applies whole.

    ``created_at`` is not touched on the update branch — the time a key first appeared
    survives any number of edits.
    """
    if not values:
        return
    async with write_scope() as s:
        insert = _insert_for(s)
        now = utc_now()
        stmt = insert(InterfaceSetting).values(
            [
                {"key": key, "value": value, "created_at": now, "updated_at": now}
                for key, value in values.items()
            ]
        )
        stmt = stmt.on_conflict_do_update(
            index_elements=["key"],
            set_={"value": stmt.excluded.value, "updated_at": now},
        )
        await s.execute(stmt)


async def delete_many(keys: Sequence[str]) -> None:
    """Drop overrides: the rows disappear and the registry default applies again."""
    if not keys:
        return
    async with write_scope() as s:
        await s.execute(sa_delete(InterfaceSetting).where(InterfaceSetting.key.in_(keys)))


async def delete_all() -> None:
    async with write_scope() as s:
        await s.execute(sa_delete(InterfaceSetting))


async def prune_unknown(known_keys: Sequence[str]) -> int:
    """Remove rows whose keys are outside the registry; return their count for the startup log.

    Otherwise a setting retired along with a frontend version would stay in the database forever.
    """
    async with write_scope() as s:
        result = await s.execute(
            sa_delete(InterfaceSetting).where(InterfaceSetting.key.not_in(known_keys))
        )
        return result.rowcount or 0


__all__ = ["list_all", "upsert_many", "delete_many", "delete_all", "prune_unknown"]
