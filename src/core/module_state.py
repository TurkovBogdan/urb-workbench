"""Accessor for a module's arbitrary state (``core_modules_state``).

``module_store(code)`` returns a ``ModuleStore`` with the module code baked in, so that
``module=`` need not be passed to every call:

    store = module_store("mail_sync")
    await store.set("gmail_import_cursor", {"history_id": "98213"})
    cursor = await store.get("gmail_import_cursor")   # -> dict | None

A thin wrapper over ``crud/module_state.py``; the place for internal runtime state
(cursors, counters, markers), not for user configuration (that goes in settings).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from src.core.crud import module_state as crud


@dataclass(frozen=True)
class ModuleStore:
    """State store of a single module. The module code is bound to the instance."""

    module: str

    async def get(self, code: str, default: Any = None) -> Any:
        row = await crud.get_one(self.module, code)
        return row.value if row is not None else default

    async def set(self, code: str, value: Any) -> None:
        await crud.upsert(self.module, code, value)

    async def seed_if_absent(self, code: str, value: Any) -> bool:
        return await crud.seed_if_absent(self.module, code, value)

    async def delete(self, code: str) -> None:
        await crud.delete(self.module, code)

    async def all(self) -> dict[str, Any]:
        rows = await crud.list_for_module(self.module)
        return {row.code: row.value for row in rows}


def module_store(module: str) -> ModuleStore:
    return ModuleStore(module=module)


__all__ = ["ModuleStore", "module_store"]
