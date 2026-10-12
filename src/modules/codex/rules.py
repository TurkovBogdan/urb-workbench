"""What a codex tree may hold — one answer for the person's interface and for the agent.

The rules belong to the data, not to whoever writes it (the same split as ``tasks/rules.py``): the
decision lives here, the wording of a refusal at each surface. The services in ``crud/`` enforce
them; ``workbench`` asks them before it writes for the agent.

- **A segment** is one step of a path: lower-case Latin letters, digits, hyphens and underscores —
  the set of the app's shared validator (`web/src/shared/utils/validators.ts`) — starting with a
  letter or digit. It is typed into paths by hand, so nothing needs escaping or quoting.
- **Depth** is at most four levels, the codex itself counted: ``codex / note / note / note``. Past
  that a tree stops being browsable from an index, and a deeper split is a sign the codex wants
  dividing, not another level.
- **The agent writes notes, never a codex,** and only where the mount lets it.
"""

from __future__ import annotations

import re

from src.modules.codex.constants import SEGMENT_MAX
from src.modules.codex.models import CodexMount

SEGMENT_PATTERN = re.compile(r"[a-z0-9][a-z0-9_-]*")

# The codex is level 1, a top-level note level 2.
DEPTH_MAX = 4
TOP_NOTE_DEPTH = 2


def segment_problem(segment: str) -> str | None:
    """Why ``segment`` cannot be a path segment, or ``None`` when it can."""
    if not segment:
        return "the segment is empty"
    if len(segment) > SEGMENT_MAX:
        return f"the segment is {len(segment)} characters long, the limit is {SEGMENT_MAX}"
    if not SEGMENT_PATTERN.fullmatch(segment):
        return (
            f"the segment {segment!r} may hold only a-z, 0-9, '_' and '-', and must start with a "
            "letter or a digit"
        )
    return None


def depth_problem(parent_depth: int, branch_height: int = 1) -> str | None:
    """Why a branch ``branch_height`` levels tall cannot hang under a node at ``parent_depth``.

    A new note is a branch of height 1; moving a note takes its whole subtree along.
    """
    deepest = parent_depth + branch_height
    if deepest <= DEPTH_MAX:
        return None
    return (
        f"the tree would reach {deepest} levels, the limit is {DEPTH_MAX} "
        f"(codex / note / note / note) — {deepest - DEPTH_MAX} too deep"
    )


def agent_may_write(mount: CodexMount | None) -> bool:
    """Whether the agent may write notes of a codex through this mount; no mount — not visible."""
    return mount is not None and mount.agent_can_edit


__all__ = [
    "DEPTH_MAX",
    "SEGMENT_PATTERN",
    "TOP_NOTE_DEPTH",
    "agent_may_write",
    "depth_problem",
    "segment_problem",
]
