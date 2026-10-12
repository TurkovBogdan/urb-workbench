"""``core_lookup`` test fixtures: an empty registry of its own for every test.

The registry is process-wide, and the assembled app fills it with the real modules' types; a test
that registers a fake handler must not leak it into the next one, nor see what an app built
earlier left behind.
"""

from __future__ import annotations

import pytest

from src.modules.core_lookup import registry


@pytest.fixture(autouse=True)
def lookup_registry(monkeypatch: pytest.MonkeyPatch) -> dict:
    fresh: dict = {}
    monkeypatch.setattr(registry, "_BY_WORD", fresh)
    return fresh
