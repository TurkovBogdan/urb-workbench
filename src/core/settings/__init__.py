"""Public API of the runtime user-tunable settings subsystem.

Re-exports the field types and the accessor for the current per-module store. The
internals are split across the package's modules (fields, schema, store, registry,
bootstrap, api).
"""

from __future__ import annotations

from typing import Any

from src.core.settings.fields import (
    BoolField,
    ChoiceField,
    DateField,
    DateTimeField,
    Field,
    FloatField,
    IntField,
    ListField,
    MultiChoiceField,
    StrField,
    VisibleWhen,
)
from src.core.settings.registry import get_registry
from src.core.settings.schema import ModuleSchema


def get_module_store(module: str) -> Any:
    """The module's current immutable store. RuntimeError if not loaded yet."""
    return get_registry().get(module)


__all__ = [
    "BoolField",
    "ChoiceField",
    "DateField",
    "DateTimeField",
    "Field",
    "FloatField",
    "IntField",
    "ListField",
    "ModuleSchema",
    "MultiChoiceField",
    "StrField",
    "VisibleWhen",
    "get_module_store",
]
