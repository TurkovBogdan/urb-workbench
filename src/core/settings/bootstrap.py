"""Two-phase initialisation of the settings subsystem.

- ``register_settings_schemas`` (sync) — in ``create_app`` BEFORE ``Module.configure``.
- ``load_initial_stores`` (async) — in the lifespan AFTER ``AlembicRunner.upgrade_head``.
"""

from __future__ import annotations

from collections.abc import Sequence

from src.core.settings.registry import get_registry
from src.core.module import Module


def register_settings_schemas(modules: Sequence[Module]) -> None:
    """Build phase: register the modules' schemas and instances in the registry."""
    reg = get_registry()
    for m in modules:
        if m.settings_schema is None:
            continue
        reg.register_schema(m)


async def load_initial_stores(modules: Sequence[Module]) -> None:
    """Runtime phase: seed defaults + install initial store per module."""
    reg = get_registry()
    for m in modules:
        if m.settings_schema is None:
            continue
        await reg.load_initial(m.name)


__all__ = ["register_settings_schemas", "load_initial_stores"]
