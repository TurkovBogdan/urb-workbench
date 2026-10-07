"""Workspace content counters — the hook through which the modules above extend its card.

A workspace itself does not know what lives in it: zones and tasks are the ``tasks`` module's
business, documents will be another module's, and the "how much is inside" list cannot be
hardwired here, otherwise the dependency would run top-down — from level 1 to level 2.

So a counter is **registered**: a module above declares, in its ``configure()``, a key, a label
key for the interface and a function that counts its rows for a list of workspace codes at once.
The workspace card shows whatever is registered and knows nothing about the entities themselves.

We count in a batch (``codes -> {code: count}``), not per row: the workspace list fits on one
screen, and a query per card would make N+1 where a single grouping is enough.

A counter's label does not arrive as a string: the backend returns the message KEY
(``label_key``), and the interface supplies the text. Otherwise Russian text would settle in a
module that knows nothing about language, owned by someone other than the owner of the entity.

The registry is process-global, like the scheduler's job registry: ``configure()`` is called once
per application build, and a repeated build (tests bring the app up many times) overwrites the
entry by key instead of piling up duplicates.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field

CountByCodes = Callable[[list[str]], Awaitable[dict[str, int]]]


@dataclass(frozen=True)
class WorkspaceCounter:
    """A counter declaration: what to count with, what to call it and in which order to show it."""

    key: str
    """The counter's key in the API response (``groups``/``tasks``); unique across the app."""

    label_key: str
    """The interface message key for the label — owned by the module that created the counter."""

    count_by_codes: CountByCodes = field(compare=False)
    """``[workspace code, …] -> {code: how many}``. Workspaces without rows may be omitted."""

    sort: int = 500
    """Higher goes first — the order on the card is set by whoever registers the counter."""


_REGISTRY: dict[str, WorkspaceCounter] = {}


def register_counter(counter: WorkspaceCounter) -> None:
    """Declare a workspace content counter (registering a key again replaces it)."""
    _REGISTRY[counter.key] = counter


def registered_counters() -> list[WorkspaceCounter]:
    """The declared counters: higher ``sort`` first, then by key — the order is stable."""
    return sorted(_REGISTRY.values(), key=lambda counter: (-counter.sort, counter.key))


async def counts_for(codes: list[str]) -> dict[str, dict[str, int]]:
    """``workspace code -> {counter key: how many}`` for all declared counters.

    The zero is filled in here, not in the counting function: "not returned" and "found nothing"
    are the same answer for the card, and requiring every module to fill in zeros would mean
    repeating the same assembly in each of them.
    """
    if not codes:
        return {}
    counters = registered_counters()
    counted = {counter.key: await counter.count_by_codes(codes) for counter in counters}
    return {
        code: {counter.key: counted[counter.key].get(code, 0) for counter in counters}
        for code in codes
    }


def reset_counters() -> None:
    """Clear the registry — for tests that need a card without other modules' counters."""
    _REGISTRY.clear()


__all__ = [
    "WorkspaceCounter",
    "counts_for",
    "register_counter",
    "registered_counters",
    "reset_counters",
]
