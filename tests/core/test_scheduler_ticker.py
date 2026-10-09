"""Tests for Ticker.

Coverage:
- ``_tick_once`` spawns due tasks and skips non-due ones (through a registered handler).
- ``_tick_once`` cleans up zombies: their tasks are finalized with error and their locks released.
- ``start`` is idempotent (a repeated call is a no-op).
- ``stop`` waits for active run_entry calls within the grace period.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select, update

from src.core.config import Config
from src.core.crud import tasks as crud_tasks
from src.core.database import close_database, init_database, session_scope, write_scope
from src.core.locks import CoreLock, CoreLockRow
from src.core.models.tasks import CoreTask, CoreTaskStatus
from src.core.scheduler.registry import get_registry
from src.core.scheduler.ticker import Ticker



@pytest.fixture
async def db(config: Config):
    engine = await init_database(config)
    from src.core.database.runtime import Base

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    get_registry().clear()
    try:
        yield
    finally:
        get_registry().clear()
        await close_database()


# ── _tick_once: spawning due tasks ──────────────────────────────────────────


@pytest.mark.db
async def test_tick_spawns_due_entry(db):
    ran = asyncio.Event()

    async def handler(ctx):
        ran.set()

    get_registry().register(
        module="m", code="c", name="Demo", description="d",
        schedule="* * * * *", handler=handler, ttl=60, enabled=True,
    )

    ticker = Ticker()
    await ticker._tick_once()
    await asyncio.wait_for(asyncio.gather(*ticker._active), timeout=5)
    assert ran.is_set()
    async with session_scope() as s:
        task = (await s.execute(select(CoreTask))).scalar_one()
    assert task.status == CoreTaskStatus.success


@pytest.mark.db
async def test_tick_skips_not_due_entry(db):
    ran = asyncio.Event()

    async def handler(ctx):  # pragma: no cover - must not fire
        ran.set()

    # runs once an hour → not due right after the fixture's last_run
    get_registry().register(
        module="m", code="c", name="Demo", description="d",
        schedule="0 * * * *", handler=handler, ttl=60, enabled=True,
    )
    async with write_scope() as s:
        await s.execute(
            CoreTask.__table__.insert().values(
                status=CoreTaskStatus.success,
                module="m",
                code="c",
                started_at=datetime.now(timezone.utc).replace(tzinfo=None),
                finished_at=datetime.now(timezone.utc).replace(tzinfo=None),
            )
        )

    ticker = Ticker()
    await ticker._tick_once()
    assert ticker._active == set()
    assert not ran.is_set()


# ── _tick_once: module scope ─────────────────────────────────────────────────


@pytest.mark.db
async def test_tick_scope_filters_by_module(db):
    """Ticker(modules={a}) spawns only module a's tasks and skips b."""
    ran: set[str] = set()

    def make(tag: str):
        async def handler(ctx):
            ran.add(tag)
        return handler

    get_registry().register(
        module="a", code="c", name="A", description="d",
        schedule="* * * * *", handler=make("a"), ttl=60, enabled=True,
    )
    get_registry().register(
        module="b", code="c", name="B", description="d",
        schedule="* * * * *", handler=make("b"), ttl=60, enabled=True,
    )

    ticker = Ticker(modules=frozenset({"a"}))
    await ticker._tick_once()
    await asyncio.wait_for(asyncio.gather(*ticker._active), timeout=5)
    assert ran == {"a"}
    async with session_scope() as s:
        tasks = (await s.execute(select(CoreTask))).scalars().all()
    assert {t.module for t in tasks} == {"a"}


# ── _tick_once: zombie cleanup ──────────────────────────────────────────────


@pytest.mark.db
async def test_tick_cleans_zombie_and_releases_its_locks(db):
    zombie_id = await crud_tasks.create_running(module="z", code="z")
    async with write_scope() as s:
        await s.execute(
            update(CoreTask)
            .where(CoreTask.id == zombie_id)
            .values(heartbeat_at=datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(seconds=600))
        )
    lock = await CoreLock.acquire("res:zombie", 60, owner=f"task_run:{zombie_id}")
    assert lock is not None
    foreign = await CoreLock.acquire("res:foreign", 60, owner="external")
    assert foreign is not None

    ticker = Ticker(zombie_threshold=90)
    await ticker._tick_once()

    async with session_scope() as s:
        task = (
            await s.execute(select(CoreTask).where(CoreTask.id == zombie_id))
        ).scalar_one()
        locks = (await s.execute(select(CoreLockRow))).scalars().all()
    assert task.status == CoreTaskStatus.error
    assert "orphaned" in (task.error_text or "")
    assert {l.key for l in locks} == {"res:foreign"}


# ── start / stop ────────────────────────────────────────────────────────────


@pytest.mark.db
async def test_start_is_idempotent(db):
    ticker = Ticker(tick_seconds=3600)
    try:
        await ticker.start()
        first = ticker._task
        await ticker.start()
        assert ticker._task is first
    finally:
        await ticker.stop()
    assert ticker._task is None


@pytest.mark.db
async def test_stop_waits_for_active_runs_within_grace(db):
    started = asyncio.Event()
    finished = asyncio.Event()

    async def handler(ctx):
        started.set()
        await asyncio.sleep(0.2)
        finished.set()

    get_registry().register(
        module="m", code="c", name="Demo", description="d",
        schedule="* * * * *", handler=handler, ttl=60, enabled=True,
    )

    ticker = Ticker(tick_seconds=3600, shutdown_grace_seconds=5)
    await ticker._tick_once()
    await asyncio.wait_for(started.wait(), timeout=5)
    await ticker.stop()
    assert finished.is_set()
    async with session_scope() as s:
        task = (await s.execute(select(CoreTask))).scalar_one()
    assert task.status == CoreTaskStatus.success


# ── scheduler.start: worker-override ─────────────────────────────────────────


@pytest.mark.db
async def test_start_skipped_when_worker_disabled(db, config: Config):
    """Without an override and with worker_enabled=false the ticker does not start."""
    from src.core import scheduler

    cfg = Config(_env_file=None, db_host="x", db_name="x", db_user="x",
                 db_password="x", db_ssl=False, worker_enabled=False)
    await scheduler.start(cfg)
    try:
        assert scheduler._TICKER is None
    finally:
        await scheduler.stop()


@pytest.mark.db
async def test_configure_worker_forces_ticker(db):
    """configure_worker forces the ticker to start even with worker_enabled=false."""
    from src.core import scheduler

    cfg = Config(_env_file=None, db_host="x", db_name="x", db_user="x",
                 db_password="x", db_ssl=False, worker_enabled=False)
    scheduler.configure_worker(modules=frozenset({"a"}), max_concurrent=3, tick=3600)
    await scheduler.start(cfg)
    try:
        assert scheduler._TICKER is not None
        assert scheduler._TICKER.modules == frozenset({"a"})
    finally:
        await scheduler.stop()
    # stop() clears the override → the next start without it does not bring up the ticker.
    assert scheduler._WORKER_OVERRIDE is None
