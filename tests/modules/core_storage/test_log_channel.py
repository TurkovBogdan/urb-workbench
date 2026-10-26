"""The module's log channel is named in one place: a second caller spelling it by hand is how half
of the journal ends up in another file after a rename."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from src.modules.core_storage.constants import LOG_CHANNEL

pytestmark = pytest.mark.pure

_PACKAGE = Path(__file__).resolve().parents[3] / "src" / "modules" / "core_storage"
_CALL = re.compile(r"get_logger\(([^)]*)\)")


def test_every_logger_of_the_module_takes_the_channel_constant():
    calls = {
        path.relative_to(_PACKAGE).as_posix(): _CALL.findall(path.read_text(encoding="utf-8"))
        for path in _PACKAGE.rglob("*.py")
    }
    found = {name: args for name, args in calls.items() if args}

    assert len(found) >= 4  # positive control: the sweep reached the files that log
    assert {name: args for name, args in found.items() if args != ["LOG_CHANNEL"]} == {}


def test_the_channel_is_the_module_name():
    assert LOG_CHANNEL == "core_storage"
