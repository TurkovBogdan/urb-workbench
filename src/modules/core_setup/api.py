"""HTTP API for the environment settings (mounted at /internal/core/setup).

``GET`` — fields by group with their current values from ``.env``. ``PUT`` — write the given
values into ``.env`` and restart the process (the fresh start re-reads Config); ``moves_to`` in
the reply names the new host/port when the restarted process will listen elsewhere.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Request
from pydantic import BaseModel

from src.core.router.guards import guard
from src.modules.core_setup import env_file, restart
from src.modules.core_setup.keys import FIELD_BY_KEY, FIELDS, GROUP_LABELS

router = APIRouter()


def _groups_payload() -> list[dict[str, Any]]:
    values = env_file.read_values([f.key for f in FIELDS])
    groups: dict[str, list[dict[str, Any]]] = {}
    for f in FIELDS:
        groups.setdefault(f.group, []).append(
            {
                "key": f.key,
                "type": f.type,
                "label": f.label,
                "description": f.description,
                "choices": list(f.choices),
                "secret": f.secret,
                "value": values.get(f.key, ""),
                "visible_when": (
                    {"key": f.visible_when.key, "equals": f.visible_when.equals}
                    if f.visible_when is not None
                    else None
                ),
            }
        )
    return [
        {"code": group, "group": GROUP_LABELS[group], "fields": fields}
        for group, fields in groups.items()
    ]


class _ApplyBody(BaseModel):
    values: dict[str, str]


@router.get("")
async def get_setup() -> dict[str, Any]:
    return {"groups": _groups_payload()}


@router.put("")
@guard("allow_all")
async def apply_setup(body: _ApplyBody, request: Request) -> dict[str, Any]:
    updates = {k: v for k, v in body.values.items() if k in FIELD_BY_KEY}
    env_file.write_values(updates)
    config = request.app.state.config
    moves_to = restart.predict_move(
        hot_reload=config.server_hot_reload,
        bound_host=config.server_host,
        bound_port=config.server_port,
    )
    restart.schedule_restart(hot_reload=config.server_hot_reload)
    return {"status": "restarting", "applied": sorted(updates), "moves_to": moves_to}


__all__ = ["router"]
