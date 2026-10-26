"""The id of this installation — so an import tells its own archive from someone else's.

It lives in the shared module state store: an internal mark, not an operator's setting, and
nobody needs to see or change it.
"""

from __future__ import annotations

from ulid import ULID

from src.core.module_state import module_store
from src.modules.core_transfer.constants import INSTALL_ID_KEY, MODULE_NAME


async def install_id() -> str:
    store = module_store(MODULE_NAME)
    existing = await store.get(INSTALL_ID_KEY)
    if existing:
        return str(existing)
    await store.seed_if_absent(INSTALL_ID_KEY, str(ULID()))
    return str(await store.get(INSTALL_ID_KEY))


__all__ = ["install_id"]
