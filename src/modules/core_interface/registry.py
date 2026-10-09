"""The interface settings registry: the only place where keys and defaults are declared.

Three things are known about a setting here: its default (which also defines its type), the
set of allowed values, and a predicate for cases a set cannot describe. How a setting looks on
screen — label, group, order — the registry does not know: the frontend assembles the UI, and
the server stays a store that can refuse.

Defaults are not written to the database. A row appears only for a deviation, so changing a
default here reaches an installation instantly: whoever never touched the setting simply has
no row, and reads the new value.

The map closes the key space: an unknown key is rejected rather than creating a row.
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any

from src.modules.core_interface.constants import KEY_MAX_LENGTH, VALUE_MAX_BYTES

TYPE_STRING = "string"
TYPE_NUMBER = "number"
TYPE_BOOLEAN = "boolean"


@dataclass(frozen=True)
class Setting:
    """A setting declaration: the default plus an optional constraint on the value."""

    default: Any
    options: tuple[Any, ...] | None = None
    check: Callable[[Any], bool] | None = None


# The ``interface_`` prefix is not a check (the map itself closes the key space) but a mark of
# ownership: the name shows whether a key governs the application's look or something else.
SETTINGS: dict[str, Setting] = {
    # The human's interface language. It does not govern the agent surface (MCP) — always English.
    "interface_language": Setting("en", options=("en", "ru")),
    "interface_theme":Setting("dark", options=("dark", "light", "system")),
    "interface_font": Setting("onest"),
    "interface_font_reading": Setting("onest"),
    # ``reading`` is not a typeface but "same as the body font": headings follow it when it changes.
    "interface_font_heading": Setting("reading"),
    "interface_font_reading_size": Setting(14, options=(14, 15, 16, 17, 18, 20)),
    "interface_font_reading_weight": Setting(300, options=(100, 200, 300, 400, 500, 600, 700, 800, 900)),
    "interface_font_heading_weight": Setting(600, options=(100, 200, 300, 400, 500, 600, 700, 800, 900)),
    "interface_font_reading_measure": Setting(92, options=(64, 76, 92, 108, 124, 0)),
    "interface_font_mono": Setting("jetbrains-mono"),
    "interface_code_variant": Setting("minimal", options=("icon", "accent", "minimal")),
    "interface_font_code_size": Setting(12, options=(11, 12, 13, 14, 15, 16)),
    "interface_code_line_numbers": Setting(True),
    "interface_font_diagram": Setting("onest"),
    # ``system`` — the application's colours; the rest are the diagram engine's ready palettes.
    "interface_diagram_theme": Setting(
        "system",
        options=(
            "system",
            "zinc-light",
            "zinc-dark",
            "github-light",
            "github-dark",
            "tokyo-night",
            "tokyo-night-storm",
            "tokyo-night-light",
            "catppuccin-mocha",
            "catppuccin-latte",
            "nord",
            "nord-light",
            "dracula",
            "solarized-light",
            "solarized-dark",
            "one-dark",
        ),
    ),
    "interface_diagram_align": Setting("left", options=("left", "center")),
    "interface_diagram_max_height": Setting(420, options=(280, 420, 560, 0)),
    "interface_sidebar_collapsed": Setting(False),
}

_KEY_PATTERN = re.compile(r"^[a-z][a-z0-9_]*$")


def validate_registry() -> None:
    """Self-check of the map at module startup: a malformed key fails the start, not the first
    request."""
    for key, setting in SETTINGS.items():
        if not _KEY_PATTERN.match(key):
            raise ValueError(f"core_interface: key {key!r} is not a snake_case identifier")
        if len(key) > KEY_MAX_LENGTH:
            raise ValueError(f"core_interface: key {key!r} is longer than {KEY_MAX_LENGTH} chars")
        refusal = rejection(key, setting.default)
        if refusal is not None:
            raise ValueError(
                f"core_interface: the default of {key!r} fails its own check — {refusal}"
            )


UNKNOWN_SETTING = "unknown setting"
NOT_AN_OPTION = "value is not one of the allowed options"
CHECK_FAILED = "value failed the check"


def rejection(key: str, value: Any) -> str | None:
    """The reason for refusal, or ``None`` if the value is accepted.

    The reason is English text: the interface client syncs settings silently and uses it only
    to drop the key from its queue; it is never shown to a human.

    The checks go from general to specific: each one makes sense only after the previous one
    (there is no point matching a value of the wrong type against the option set).
    """
    setting = SETTINGS.get(key)
    if setting is None:
        return UNKNOWN_SETTING
    if not matches_default_type(value, setting.default):
        return f"expected a {value_type(setting.default)} value"
    if setting.options is not None and value not in setting.options:
        return NOT_AN_OPTION
    if setting.check is not None and not setting.check(value):
        return CHECK_FAILED
    if _serialized_size(value) > VALUE_MAX_BYTES:
        return f"value is longer than {VALUE_MAX_BYTES} bytes"
    return None


def matches_default_type(value: Any, default: Any) -> bool:
    """The value's type is defined by the default — a setting carries no separate type mark.

    ``bool`` is checked first: in Python it is a subclass of ``int``, and without an explicit
    exclusion ``True`` would pass as a number and ``1`` as a toggle.
    """
    if isinstance(default, bool):
        return isinstance(value, bool)
    if isinstance(default, (int, float)):
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    return isinstance(value, str)


def value_type(default: Any) -> str:
    if isinstance(default, bool):
        return TYPE_BOOLEAN
    if isinstance(default, (int, float)):
        return TYPE_NUMBER
    return TYPE_STRING


def schema() -> list[dict[str, Any]]:
    """A machine description of the fields in declaration order: type, default, option set.

    The ``check`` predicate is not included: it answers yes/no and cannot be described as data.
    Where the set must be visible to a human, ``options`` is declared.
    """
    return [
        {
            "key": key,
            "type": value_type(setting.default),
            "default": setting.default,
            "options": list(setting.options) if setting.options is not None else None,
        }
        for key, setting in SETTINGS.items()
    ]


def effective_values(stored: Mapping[str, Any]) -> dict[str, Any]:
    """Effective values of all fields: the default wherever there is no deviation."""
    return {key: stored.get(key, setting.default) for key, setting in SETTINGS.items()}


def unknown_keys(keys: Mapping[str, Any] | list[str]) -> list[str]:
    return [key for key in keys if key not in SETTINGS]


def _serialized_size(value: Any) -> int:
    return len(json.dumps(value, ensure_ascii=False).encode())


__all__ = [
    "CHECK_FAILED",
    "NOT_AN_OPTION",
    "Setting",
    "SETTINGS",
    "TYPE_BOOLEAN",
    "TYPE_NUMBER",
    "TYPE_STRING",
    "UNKNOWN_SETTING",
    "effective_values",
    "matches_default_type",
    "rejection",
    "schema",
    "unknown_keys",
    "validate_registry",
    "value_type",
]
