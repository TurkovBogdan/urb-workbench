"""Per-module immutable store — a frozen dataclass codegen'd from ModuleSchema."""

from __future__ import annotations

from dataclasses import make_dataclass
from typing import Any

from src.core.settings.fields import ListField, MultiChoiceField
from src.core.settings.schema import ModuleSchema


ModuleSettingsStore = Any
"""Type of a per-module store. The concrete class is codegen'd in build_store."""


def _freeze(value: Any, field) -> Any:
    """list/multichoice → tuple, so the instance is fully immutable."""
    if isinstance(field, (ListField, MultiChoiceField)):
        return tuple(value)
    return value


def build_store(
    module: str,
    schema: ModuleSchema,
    values: dict[str, Any],
) -> ModuleSettingsStore:
    """Construct a frozen dataclass instance from the values, per the schema.

    Missing keys are filled with ``field.default()`` (the caller is expected to
    log a warning in that case).
    """
    cls = make_dataclass(
        f"_{module.title().replace('_', '')}SettingsStore",
        [(f.key, Any) for f in schema],
        frozen=True,
    )
    kwargs = {}
    for f in schema:
        raw = values.get(f.key, f.default())
        kwargs[f.key] = _freeze(raw, f)
    return cls(**kwargs)


__all__ = ["ModuleSettingsStore", "build_store"]
