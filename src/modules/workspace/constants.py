"""Constants of the ``workspace`` module — code length, prefix and card field sizes.

A single source for three places that must agree: the ORM model (``String(n)``), the migration
and truncation in the CRUD (``text.clip``). Were they to drift apart, the mismatch would surface
only on PostgreSQL: SQLite does not check ``VARCHAR`` width at all.

``CODE_LEN`` is a contract NOT of this module alone: foreign codes from the modules above refer
to the workspace (``tasks_group.workspace_code`` and its neighbours), and their column width is
taken from here. Changing the length means changing it in every referring table in one
migration.
"""

from __future__ import annotations

# ── presentation code prefix (boundary, NOT store — see workspace.codes) ──
# The database holds the bare hex code; the type word is added on output and stripped on input.
WORKSPACE_CODE_PREFIX = "WORKSPACE"

# Code length in hex characters. The same as the entities of the modules above: the workspace
# code goes into their tables, and different column widths for one and the same code are a
# truncated reference waiting to happen.
CODE_LEN = 10

# ── text column sizes ──
TITLE_MAX = 96
# A workspace's description is a line under its name in the cards and the switcher — what it is
# for, not a paragraph about it. Over the limit is refused, not cut (``text.fit``).
DESCRIPTION_MAX = 128
COLOR_MAX = 32
ICON_MAX = 64

# ── list position ──
# The same scale as a task group's (``tasks.constants``): higher ``sort`` = higher up, a non-zero
# start so the first row can move both ways, a step that leaves room between neighbours.
SORT_DEFAULT = 500
SORT_STEP = 5


__all__ = [
    "CODE_LEN",
    "COLOR_MAX",
    "DESCRIPTION_MAX",
    "ICON_MAX",
    "SORT_DEFAULT",
    "SORT_STEP",
    "TITLE_MAX",
    "WORKSPACE_CODE_PREFIX",
]
