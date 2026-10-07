"""The module's request and response bodies.

The schema is assembled from the registry on the fly, so it needs no storage of its own and
cannot drift from the check applied on write.

The schema field is called ``schema`` outwardly and ``fields`` inside: the name ``schema`` is
taken by a method of ``BaseModel`` itself, and pydantic accepts a field by that name only with
a warning.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class SettingSchemaOut(BaseModel):
    key: str
    type: str  # string | number | boolean
    default: Any
    options: list[Any] | None  # ``null`` — the set is unrestricted


class InterfaceSettingsOut(BaseModel):
    """Effective values of all fields; the schema only on the startup request."""

    values: dict[str, Any]
    fields: list[SettingSchemaOut] | None = Field(default=None, serialization_alias="schema")


class InterfaceSchemaOut(BaseModel):
    fields: list[SettingSchemaOut] = Field(serialization_alias="schema")


class InterfaceSettingsPatch(BaseModel):
    values: dict[str, Any]


class InterfaceSettingsReset(BaseModel):
    keys: list[str]


__all__ = [
    "InterfaceSchemaOut",
    "InterfaceSettingsOut",
    "InterfaceSettingsPatch",
    "InterfaceSettingsReset",
    "SettingSchemaOut",
]
