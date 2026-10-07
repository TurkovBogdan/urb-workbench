"""Database runtime: declarative base, engine/session, lifecycle.

One process, one engine. The session factory and the engine live at module level;
``init_database`` creates them, ``close_database`` resets them.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import AsyncIterator

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

from src.core.config import Config
from src.core.database.sqlite import WRITE_EXECUTION_OPTIONS, configure_sqlite


# ── Declarative base ─────────────────────────────────────────────────────────

class Base(DeclarativeBase):
    """Root SQLAlchemy declarative base for every ORM model."""

    def to_row(self, skip: frozenset[str] = frozenset()) -> dict:
        """Serialize to a dict keyed by the table's columns. Used by upsert."""
        return {
            c.name: getattr(self, c.name)
            for c in self.__table__.columns
            if c.name not in skip
        }


# ── Module-level engine/factory ──────────────────────────────────────────────

_engine: AsyncEngine | None = None
_session_factory: async_sessionmaker[AsyncSession] | None = None


async def init_database(config: Config) -> AsyncEngine:
    """Create the engine + session factory. Idempotent on a repeated call."""
    # Importing the models registers them in ``Base.metadata``.
    # Done lazily to avoid a circular import at module load.
    import src.core.models  # noqa: F401

    global _engine, _session_factory
    if _engine is not None:
        await _engine.dispose()
    _engine = create_async_engine(
        config.database_url,
        echo=config.db_echo,
        future=True,
        **config.engine_kwargs,
    )
    configure_sqlite(_engine, config)
    _session_factory = async_sessionmaker(
        bind=_engine,
        autoflush=False,
        expire_on_commit=False,
    )
    return _engine


async def close_database() -> None:
    """Close the engine and reset the factory."""
    global _engine, _session_factory
    if _engine is not None:
        await _engine.dispose()
    _engine = None
    _session_factory = None


def get_engine() -> AsyncEngine | None:
    """The current engine, or None if ``init_database`` has not been called."""
    return _engine


async def create_all(engine: AsyncEngine) -> None:
    """Create every table from the ORM models (test in-memory SQLite only; file DBs use Alembic).

    Relies on a populated ``Base.metadata`` — modules that own tables must be imported by
    this point (just as ``init_database`` pulls in ``src.core.models``).
    """
    import src.core.models  # noqa: F401  (registers the core models in Base.metadata)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


# ── Session access ───────────────────────────────────────────────────────────

@asynccontextmanager
async def session_scope() -> AsyncIterator[AsyncSession]:
    """Read-only transactional scope. A mutating statement inside it is an error."""
    async with _scope(writing=False) as session:
        yield session


@asynccontextmanager
async def write_scope() -> AsyncIterator[AsyncSession]:
    """Writing transactional scope: on SQLite the transaction opens with ``BEGIN IMMEDIATE``.

    The intent is declared before the first statement; otherwise a transaction that began
    with a read cannot be promoted to a write — the refusal arrives without waiting on the
    lock (``database/sqlite.py``).
    """
    async with _scope(writing=True) as session:
        yield session


@asynccontextmanager
async def _scope(*, writing: bool) -> AsyncIterator[AsyncSession]:
    assert _session_factory is not None, "init_database() not called"
    session = _session_factory()
    try:
        if writing:
            await session.connection(execution_options=WRITE_EXECUTION_OPTIONS)
        yield session
        await session.commit()
    except Exception:
        await session.rollback()
        raise
    finally:
        await session.close()


__all__ = [
    "Base",
    "close_database",
    "get_engine",
    "init_database",
    "session_scope",
    "write_scope",
]
