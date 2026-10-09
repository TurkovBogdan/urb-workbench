"""HTTP API of the settings subsystem (mounted at /internal/core/settings)."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from src.core.api import ApiError
from src.core.router import guard
from src.core.settings.registry import get_registry
from src.core.settings.schema import field_by_key


router = APIRouter()


# A set secret is never sent out: a sentinel is returned instead of the token. The
# frontend shows the field empty (a "set" placeholder), and if it was left untouched it
# sends the same sentinel back, which is read as "don't change".
SECRET_UNCHANGED = "NOT_CHANGED"


class _ValueBody(BaseModel):
    value: Any


def _secret_placeholder(value: str) -> str:
    """Outward: empty → not set (`""`); set → the `NOT_CHANGED` sentinel (not the token)."""
    return SECRET_UNCHANGED if value else ""


def _store_values(module: str) -> dict[str, Any]:
    """Store values; secrets masked (the token is never sent out)."""
    store = get_registry().get(module)
    schema = get_registry().schema(module)
    return {
        f.key: (
            _secret_placeholder(getattr(store, f.key))
            if f.is_secret()
            else getattr(store, f.key)
        )
        for f in schema
    }


def _module_payload(module: str) -> dict[str, Any]:
    store = get_registry().get(module)
    schema = get_registry().schema(module)
    fields: list[dict[str, Any]] = []
    for f in schema:
        descriptor = f.ui_descriptor()
        if f.is_secret():
            descriptor["is_set"] = bool(getattr(store, f.key))
        fields.append(descriptor)
    return {
        "module": module,
        "description": get_registry().description(module),
        "fields": fields,
        "values": _store_values(module),
    }


@router.get("/modules")
async def list_modules() -> list[dict[str, Any]]:
    return [_module_payload(m) for m in get_registry().modules()]


@router.get("/{module}")
async def get_module(module: str) -> dict[str, Any]:
    if module not in get_registry().modules():
        raise HTTPException(status_code=404, detail="unknown module")
    return _module_payload(module)


@router.put("/{module}/{key}")
@guard("allow_all")
async def put_value(module: str, key: str, body: _ValueBody) -> dict[str, Any]:
    if module not in get_registry().modules():
        raise HTTPException(status_code=404, detail="unknown module")
    schema = get_registry().schema(module)
    try:
        field = field_by_key(schema, key)
    except KeyError:
        raise HTTPException(status_code=404, detail="unknown key")
    # A secret goes out as the sentinel/empty, so on write these values mean
    # "don't change" (otherwise the form would wipe the token). Clearing goes through reset.
    if field.is_secret() and body.value in ("", SECRET_UNCHANGED):
        return {"values": _store_values(module)}
    try:
        await get_registry().update(module, key, body.value)
    except ValueError as exc:
        raise ApiError.validation(str(exc), fields={key: str(exc)})
    return {"values": _store_values(module)}


@router.post("/{module}/{key}/reset")
@guard("allow_all")
async def reset_value(module: str, key: str) -> dict[str, Any]:
    if module not in get_registry().modules():
        raise HTTPException(status_code=404, detail="unknown module")
    schema = get_registry().schema(module)
    try:
        field_by_key(schema, key)
    except KeyError:
        raise HTTPException(status_code=404, detail="unknown key")
    await get_registry().reset(module, key)
    return {"values": _store_values(module)}


__all__ = ["router"]
