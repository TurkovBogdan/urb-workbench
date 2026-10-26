"""A conflict of codes — an entity of the archive whose code is taken here — and a person's choice.

Every entity tries to keep its code. Where the code is taken, the person chooses: «update» writes
the archive over the entity here, «replace» puts the archive's one in as new, under a new code.
Where only one makes sense — the entity here belongs to another workspace, to another holder, the
bytes differ — the conflict offers one option and says why (``reason``, a key the interface words).

Choices hang together: a note may be updated only together with its task, a record only with its
codex — otherwise it would move from the entity here to the copy. That is ``requires``: the
conflict and the choice the «update» of this one needs.

Each conflict carries the dates of both sides, so the person sees whose version is fresher.

There is no choice by default: «update» by default overwrites without consent, «replace» by
default quietly duplicates on a repeated import. ``resolve_choices`` refuses a conflict left
without one.

The plan the person saw is fingerprinted (``plan_token``): the import rebuilds the plan against
the base as it is now, and a different set of conflicts is refused rather than applied with
choices made for another one.
"""

from __future__ import annotations

import hashlib
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from typing import Any

from src.modules.core_transfer.constants import CHOICE_REPLACE, CHOICE_UPDATE, CHOICES
from src.modules.core_transfer.errors import DECISION_INVALID, TransferError


@dataclass(frozen=True)
class Side:
    """One side of a conflict as dates: when it changed, when it appeared, how large it is."""

    updated_at: str | None = None
    created_at: str | None = None
    size: int | None = None

    def as_dict(self) -> dict[str, Any]:
        return {"updated_at": self.updated_at, "created_at": self.created_at, "size": self.size}


@dataclass(frozen=True)
class Conflict:
    """An entity of the archive whose code is taken here.

    ``id`` — the archive's entity with its prefix (``NOTE@…``), unique within a plan. ``local`` —
    what holds the code here, as the person reads it: the kind, its code and title, its holder.
    """

    id: str
    entity: str
    title: str
    local: dict[str, str]
    options: tuple[str, ...]
    here: Side
    archive: Side
    reason: str = ""
    reason_params: dict[str, str] = field(default_factory=dict)
    requires: tuple[str, str] | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "entity": self.entity,
            "title": self.title,
            "local": self.local,
            "options": list(self.options),
            "reason": self.reason,
            "reason_params": self.reason_params,
            "requires": {"id": self.requires[0], "choice": self.requires[1]} if self.requires else None,
            "dates": {"local": self.here.as_dict(), "archive": self.archive.as_dict()},
        }


def only_replace(conflict_id: str, entity: str, title: str, local: dict[str, str], *,
                 here: Side, archive: Side, reason: str,
                 reason_params: dict[str, str] | None = None) -> Conflict:
    return Conflict(
        id=conflict_id,
        entity=entity,
        title=title,
        local=local,
        options=(CHOICE_REPLACE,),
        here=here,
        archive=archive,
        reason=reason,
        reason_params=reason_params or {},
    )


def both_ways(conflict_id: str, entity: str, title: str, local: dict[str, str], *,
              here: Side, archive: Side, requires: tuple[str, str] | None = None) -> Conflict:
    return Conflict(
        id=conflict_id,
        entity=entity,
        title=title,
        local=local,
        options=(CHOICE_UPDATE, CHOICE_REPLACE),
        here=here,
        archive=archive,
        requires=requires,
    )


def plan_token(conflicts: Iterable[Conflict], notices: Iterable[str] = ()) -> str:
    """The fingerprint of what the person saw: each conflict with its options, and the notices."""
    lines = sorted(
        f"{c.id}|{','.join(c.options)}|{c.requires[0] + ':' + c.requires[1] if c.requires else ''}"
        for c in conflicts
    )
    lines += sorted(notices)
    return hashlib.sha256("\n".join(lines).encode("utf-8")).hexdigest()


def resolve_choices(conflicts: Iterable[Conflict], decisions: Mapping[str, str]) -> dict[str, str]:
    """The choice for every conflict, checked; a missing or impossible one refuses the import."""
    listed = list(conflicts)
    chosen: dict[str, str] = {}
    for conflict in listed:
        choice = decisions.get(conflict.id)
        if choice is None and len(conflict.options) == 1:
            choice = conflict.options[0]
        if choice not in CHOICES or choice not in conflict.options:
            raise TransferError(
                DECISION_INVALID,
                f"No valid choice for {conflict.id}: expected one of {list(conflict.options)}",
                params={"id": conflict.id},
            )
        chosen[conflict.id] = choice
    for conflict in listed:
        if chosen[conflict.id] != CHOICE_UPDATE or conflict.requires is None:
            continue
        needed_id, needed_choice = conflict.requires
        if chosen.get(needed_id, CHOICE_UPDATE) != needed_choice:
            raise TransferError(
                DECISION_INVALID,
                f"{conflict.id} can be updated only with {needed_id} chosen as {needed_choice!r}",
                params={"id": conflict.id},
            )
    return chosen


__all__ = [
    "Conflict",
    "Side",
    "both_ways",
    "only_replace",
    "plan_token",
    "resolve_choices",
]
