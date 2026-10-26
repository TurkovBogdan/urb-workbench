"""What the lookup knows: a code prefix and the handler that answers for it.

The lookup knows no entity. Which codes it can answer for is decided by the module owning them:
in its ``configure()`` it registers the prefix and a ``preview`` handler — the same way it
declares its entities to ``core_changes``. A prefix nobody registered is "not found", not an
error: a body may quote a code of a module this installation does not run.

**The handler answers for every code it is given** — a ``Preview`` or a ``Miss`` saying why there
is none. The answer is a mapping by code, never a list: matching a batch result to its keys by
position is the classic way such a loader returns one entity's title under another's code.

**Filters are soft.** The lookup passes them to the handler as they came and does not read them:
whether ``workspace`` narrows a type, and how, is the type's own knowledge — a task carries its
workspace, a stage reaches it through its task, a codex through its mounts, a workspace is the
boundary itself.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass
from enum import StrEnum

# The filter the interface narrows every lookup by: the workspace the person works in, as a
# prefixed code. A handler whose type does not live in a workspace ignores it.
WORKSPACE_FILTER = "workspace"

# The entity whose page shows the codes (``TASK@…``, ``CODEX@…``), as a prefixed code. A handler
# whose entities sit in several places at once may prefer what this one says about them; the
# others ignore it.
HOLDER_FILTER = "holder"


class Miss(StrEnum):
    """Why a code has no preview. The values are a contract with the interface's translations."""

    NOT_FOUND = "not_found"
    FOREIGN_SCOPE = "foreign_scope"
    DELETED = "deleted"
    # Set by the lookup itself, never by a handler: the handler gave no answer for the code.
    FAILED = "failed"


@dataclass(frozen=True)
class Preview:
    """What a code is, at a glance: its title, its description and the page that shows it.

    ``link`` is an app path without the host (``/tasks/task/TASK@…``) — the interface routes by
    it, and a type whose page lives inside its owner's (a stage on its task's page) says so here.
    ``mime`` is the type of a stored file the code names, by which the interface picks its glyph;
    empty for any other code. ``held`` — the entity the request names as the page's holder holds
    the file, and the title and description are its own: the page may edit them.
    """

    title: str
    description: str = ""
    link: str = ""
    mime: str = ""
    held: bool = False


Filters = Mapping[str, str]
PreviewResult = Mapping[str, Preview | Miss]
# ``(bare codes, filters) -> {bare code: Preview | Miss}``. The codes come without the prefix and
# upper case — the form the owning module stores them in.
PreviewHandler = Callable[[list[str], Filters], Awaitable[PreviewResult]]


@dataclass(frozen=True)
class LookupType:
    """One code prefix and its handler; ``aliases`` — retired words still quoted in old bodies."""

    prefix: str
    preview: PreviewHandler
    aliases: tuple[str, ...] = ()


_BY_WORD: dict[str, LookupType] = {}


def register_type(kind: LookupType) -> None:
    """Register a prefix. Repeating the same registration (an app rebuilt in tests) is not an error;
    a second handler for a taken word is — two modules answering for one code would race."""
    words = (kind.prefix, *kind.aliases)
    for word in words:
        existing = _BY_WORD.get(word)
        if existing is not None and existing != kind:
            raise ValueError(f"Lookup prefix {word}@ is already registered for {existing.prefix}@")
    for word in words:
        _BY_WORD[word] = kind


def type_for(word: str) -> LookupType | None:
    """The type answering for a prefix word (``TASK``, or a retired ``GROUP``); ``None`` — nobody."""
    return _BY_WORD.get(word)


def registered_types() -> list[LookupType]:
    """Every registered type once, aliases folded into their type."""
    return list(dict.fromkeys(_BY_WORD.values()))


def clear_types() -> None:
    """Forget every registration — for tests that build the registry from scratch."""
    _BY_WORD.clear()


__all__ = [
    "Filters",
    "LookupType",
    "Miss",
    "Preview",
    "PreviewHandler",
    "PreviewResult",
    "HOLDER_FILTER",
    "WORKSPACE_FILTER",
    "clear_types",
    "register_type",
    "registered_types",
    "type_for",
]
