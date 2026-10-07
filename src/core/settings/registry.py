"""Runtime settings registry: schemas, current stores, on_settings_change dispatch.

Concurrency: one process — one copy of the registry. A write (update/reset) builds
a new store and atomically swaps the reference in ``self._stores[module]``. Readers
see either the old one or the new one — but always a consistent snapshot.

Tests: the module-global ``_registry`` is reset by a fixture, see
``tests/core/settings/conftest.py``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from src.core.settings.fields import Field
from src.core.settings.schema import ModuleSchema, field_by_key, validate_schema
from src.core.settings.store import build_store
from src.core.crud import module_settings as crud_settings
from src.core.loggers import get_logger

if TYPE_CHECKING:
    from src.core.module import Module

_LOG = get_logger()


class SettingsRegistry:
    def __init__(self) -> None:
        self._schemas: dict[str, ModuleSchema] = {}
        self._stores: dict[str, Any] = {}
        self._modules: dict[str, "Module"] = {}

    # ── build phase (sync) ───────────────────────────────────────────────

    def register_schema(self, module: "Module") -> None:
        """Remember the module's schema and instance. validate_schema → fail-fast."""
        assert module.settings_schema is not None
        validate_schema(module.name, module.settings_schema)
        self._schemas[module.name] = module.settings_schema
        self._modules[module.name] = module

    # ── runtime phase (async) ────────────────────────────────────────────

    async def load_initial(self, module: str) -> None:
        """Seed defaults, read them, build the store, call on_settings_change."""
        schema = self._schemas[module]
        for f in schema:
            await crud_settings.seed_if_absent(
                module=module, key=f.key, value=f.serialize(f.default())
            )
        await self._reload_and_install(module)

    async def update(self, module: str, key: str, raw_value: Any) -> Any:
        """Validate → upsert → reload → install_store. Returns the new store."""
        schema = self._schemas[module]
        f = field_by_key(schema, key)
        value = self._coerce(f, raw_value)
        f.validate(value)
        await crud_settings.upsert(
            module=module, key=key, value=f.serialize(value)
        )
        return await self._reload_and_install(module)

    async def reset(self, module: str, key: str) -> Any:
        """Write the default to the DB → reload → install_store. Returns the new store."""
        schema = self._schemas[module]
        f = field_by_key(schema, key)
        await crud_settings.upsert(
            module=module, key=key, value=f.serialize(f.default())
        )
        return await self._reload_and_install(module)

    # ── read (any phase after load_initial) ──────────────────────────────

    def get(self, module: str) -> Any:
        if module not in self._stores:
            raise RuntimeError(f"module {module!r} not yet loaded")
        return self._stores[module]

    def schema(self, module: str) -> ModuleSchema:
        return self._schemas[module]

    def description(self, module: str) -> str:
        m = self._modules.get(module)
        return m.description if m is not None else ""

    def modules(self) -> list[str]:
        return list(self._schemas.keys())

    def clear(self) -> None:
        """Reset the registry state (test fixture / rebuilding the app)."""
        self._schemas.clear()
        self._stores.clear()
        self._modules.clear()

    # ── private ──────────────────────────────────────────────────────────

    async def _reload_and_install(self, module: str) -> Any:
        schema = self._schemas[module]
        rows = await crud_settings.list_for_module(module)
        values: dict[str, Any] = {}
        known = {f.key for f in schema}
        for row in rows:
            if row.key not in known:
                _LOG.warning(
                    "settings: orphan key %s.%s in DB — ignored",
                    module, row.key,
                )
                continue
            f = field_by_key(schema, row.key)
            try:
                parsed = f.parse(row.value)
                f.validate(parsed)
                values[row.key] = parsed
            except ValueError as exc:
                _LOG.warning(
                    "settings: %s.%s corrupt (%s) — fallback to default",
                    module, row.key, exc,
                )
                default = f.default()
                values[row.key] = default
                await crud_settings.upsert(
                    module=module, key=row.key, value=f.serialize(default)
                )
        for f in schema:
            if f.key not in values:
                _LOG.warning(
                    "settings: %s.%s missing in DB — using default",
                    module, f.key,
                )
                values[f.key] = f.default()
        store = build_store(module, schema, values)
        self._install_store(module, store)
        return store

    def _install_store(self, module: str, store: Any) -> None:
        """Atomic swap + synchronous notification of the module."""
        self._stores[module] = store
        m = self._modules.get(module)
        if m is None:
            return
        try:
            m.on_settings_change(store)
        except Exception as exc:  # noqa: BLE001 — module isolation
            _LOG.exception(
                "settings: %s.on_settings_change raised %s",
                module, exc,
            )

    @staticmethod
    def _coerce(f: Field, raw: Any) -> Any:
        """Light normalisation of JSON API input: tuple→list, str→date/datetime."""
        from datetime import date, datetime
        from src.core.settings.fields import (
            DateField, DateTimeField, FloatField, IntField,
        )
        if isinstance(f, DateField) and isinstance(raw, str):
            return date.fromisoformat(raw)
        if isinstance(f, DateTimeField) and isinstance(raw, str):
            dt = datetime.fromisoformat(raw)
            if dt.tzinfo is not None:
                from datetime import timezone
                dt = dt.astimezone(timezone.utc).replace(tzinfo=None)
            return dt
        if isinstance(f, FloatField) and isinstance(raw, int) and not isinstance(raw, bool):
            return float(raw)
        if isinstance(f, IntField) and isinstance(raw, bool):
            raise ValueError(f"{f.key}: expected int, got bool")
        return raw


_registry = SettingsRegistry()


def get_registry() -> SettingsRegistry:
    return _registry


__all__ = ["SettingsRegistry", "get_registry"]
