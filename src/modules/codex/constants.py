"""Constants of the ``codex`` module — code length, prefix, field sizes and list positions.

A single source for the ORM models (``String(n)``) and, later, the services and HTTP bodies. The
migrations write the numbers out as of their date; agreement is guarded by the tests comparing the
models with the schema. A drift would surface only on PostgreSQL: SQLite does not check
``VARCHAR`` width at all.
"""

from __future__ import annotations

# One type word for both entities. A codex and a codex note are found by the same code, and the
# tools that take one take the other: the agent reads a codex as the root of its tree, and two
# words for one tree would be a choice it has to get right on every call.
CODEX_CODE_PREFIX = "CODEX"

# The same width as every other entity's code; a codex code lands in ``codex_mount`` next to a
# workspace code.
CODE_LEN = 10

# The triad is the same as a note's in ``notes``: a codex note is a document of the same size.
TITLE_MAX = 128
# "When to read this" — the line an agent decides by whether to open the record at all.
DESCRIPTION_MAX = 512
BODY_MAX = 65536

# A path segment: ``python``, ``test``. The path itself is never stored — it is assembled from the
# parents' slugs on read, so a rename or a move rewrites one row.
SLUG_MAX = 64

# Higher ``sort`` = higher up, the same convention as ``tasks``: a non-zero start lets the first
# row move both ways, and a step of 5 leaves room for four insertions between neighbours.
SORT_DEFAULT = 500
SORT_STEP = 5


__all__ = [
    "BODY_MAX",
    "CODE_LEN",
    "CODEX_CODE_PREFIX",
    "DESCRIPTION_MAX",
    "SLUG_MAX",
    "SORT_DEFAULT",
    "SORT_STEP",
    "TITLE_MAX",
]
