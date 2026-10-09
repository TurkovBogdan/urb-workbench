"""``/settings`` — interface setting values, their schema, update and reset.

Four routes for four scenarios; there is no delete endpoint — removing a setting is not a user
scenario, a human resets it to its default.

An update body is checked **as a whole** before the first write: a refusal carries all the
offending keys at once, and a half-applied batch never happens.
"""

from __future__ import annotations

from fastapi import APIRouter

from src.core.api import ApiError
from src.modules.core_interface import crud, registry
from src.modules.core_interface.dto import (
    InterfaceSchemaOut,
    InterfaceSettingsOut,
    InterfaceSettingsPatch,
    InterfaceSettingsReset,
    SettingSchemaOut,
)

internal_router = APIRouter(tags=["interface"])


@internal_router.get("/settings", response_model=InterfaceSettingsOut)
async def get_settings(include_schema: bool = False) -> InterfaceSettingsOut:
    """Effective values of all fields; ``include_schema`` adds the schema — the startup request."""
    return await _settings_out(include_schema=include_schema)


@internal_router.get("/settings/schema", response_model=InterfaceSchemaOut)
async def get_schema() -> InterfaceSchemaOut:
    """The schema on its own: it changes only on deploy, and the client caches it locally."""
    return InterfaceSchemaOut(fields=_schema())


@internal_router.patch("/settings", response_model=InterfaceSettingsOut)
async def patch_settings(body: InterfaceSettingsPatch) -> InterfaceSettingsOut:
    refusals = {
        key: reason
        for key, value in body.values.items()
        if (reason := registry.rejection(key, value)) is not None
    }
    if refusals:
        raise ApiError.validation("Settings rejected", fields=refusals)
    await crud.upsert_many(body.values)
    return await _settings_out()


@internal_router.post("/settings/reset", response_model=InterfaceSettingsOut)
async def reset_settings(body: InterfaceSettingsReset) -> InterfaceSettingsOut:
    """Drop the overrides of the listed keys — the default applies again.

    The list is mandatory: the client expresses "reset everything" as the list of all keys it
    knows from the schema. A silent "empty list = wipe everything" would be far too easy a way
    to blow away all settings.
    """
    unknown = registry.unknown_keys(body.keys)
    if unknown:
        raise ApiError.validation(
            "Settings rejected", fields={key: registry.UNKNOWN_SETTING for key in unknown}
        )
    await crud.delete_many(body.keys)
    return await _settings_out()


async def _settings_out(*, include_schema: bool = False) -> InterfaceSettingsOut:
    values = registry.effective_values(await crud.list_all())
    return InterfaceSettingsOut(values=values, fields=_schema() if include_schema else None)


def _schema() -> list[SettingSchemaOut]:
    return [SettingSchemaOut(**field) for field in registry.schema()]


__all__ = ["internal_router"]
