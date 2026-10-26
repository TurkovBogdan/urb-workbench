"""The module's runtime settings: how long an upload request stays open, whether a server path is
read.

They change from the settings page without a restart: ``on_settings_change`` hands the fresh
store to ``set_current``, and every reader asks at the moment of use — a new lifetime holds for
the next request opened, the requests already open keep the expiry they were written with. Before
the first store arrives (the build phase, tests that bring up no settings) the defaults apply.

The size ceiling is not here: it is the storage's (``core_storage`` ``max_file_size_mb``). The
storage refuses a file over it whatever the upload allows, so a ceiling of the upload's own could
only be lower — and two numbers would have to be kept in step by the person.
"""

from __future__ import annotations

from datetime import timedelta
from typing import Any

from src.core.settings import BoolField, IntField, ModuleSchema
from src.modules.core_storage_upload.constants import (
    REQUEST_TTL_MINUTES_DEFAULT,
    REQUEST_TTL_MINUTES_MAX,
    SERVER_PATH_ENABLED_DEFAULT,
)

SETTINGS_SCHEMA: ModuleSchema = (
    IntField(
        key="request_ttl_minutes",
        label="Upload request lifetime, minutes",
        description=(
            "How long an upload address stays open for a client that cannot hand the server a "
            "path. A new value holds for the next request."
        ),
        default_=REQUEST_TTL_MINUTES_DEFAULT,
        min=1,
        max=REQUEST_TTL_MINUTES_MAX,
    ),
    BoolField(
        key="server_path_enabled",
        label="Read files by a path on the server",
        description=(
            "A client may name a file on the server's disk instead of sending it. Off — the "
            "server reads no path and answers with an upload address."
        ),
        default_=SERVER_PATH_ENABLED_DEFAULT,
    ),
)

_current: Any = None


def set_current(store: Any) -> None:
    global _current
    _current = store


def _value(key: str, default: Any) -> Any:
    return default if _current is None else getattr(_current, key)


def request_ttl() -> timedelta:
    return timedelta(minutes=_value("request_ttl_minutes", REQUEST_TTL_MINUTES_DEFAULT))


def server_path_enabled() -> bool:
    return bool(_value("server_path_enabled", SERVER_PATH_ENABLED_DEFAULT))


__all__ = ["SETTINGS_SCHEMA", "request_ttl", "server_path_enabled", "set_current"]
