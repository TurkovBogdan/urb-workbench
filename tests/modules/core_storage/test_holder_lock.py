"""The holder lock: one entity's operations run one at a time, another entity's do not wait, and
an idle entity keeps no lock."""

from __future__ import annotations

import asyncio
import gc

import pytest

from src.modules.core_storage.services.holder_lock import held_locks, holder_lock, holder_locks

pytestmark = pytest.mark.pure


async def _hold(owner_id: str, entered: asyncio.Event, leave: asyncio.Event, log: list[str]):
    async with holder_lock("TASK", owner_id):
        log.append(f"in {owner_id}")
        entered.set()
        await leave.wait()
        log.append(f"out {owner_id}")


async def test_the_same_holder_waits_and_another_one_does_not():
    log: list[str] = []
    entered, leave = asyncio.Event(), asyncio.Event()
    first = asyncio.create_task(_hold("A", entered, leave, log))
    await entered.wait()

    async def same():
        async with holder_lock("TASK", "A"):
            log.append("in A again")

    async def other():
        async with holder_lock("TASK", "B"):
            log.append("in B")

    waiting = asyncio.create_task(same())
    await asyncio.wait_for(other(), timeout=1)
    await asyncio.sleep(0)
    assert log == ["in A", "in B"] and not waiting.done()

    leave.set()
    await asyncio.gather(first, waiting)
    assert log == ["in A", "in B", "out A", "in A again"]


async def test_several_holders_are_taken_together_and_a_type_is_part_of_the_key():
    async with holder_locks("TASK", ["B", "A", "B"]):
        async with holder_lock("CODEX", "A"):
            assert held_locks() == 3


async def test_no_lock_outlives_its_holders():
    async with holder_lock("TASK", "A"):
        pass
    gc.collect()
    assert held_locks() == 0
