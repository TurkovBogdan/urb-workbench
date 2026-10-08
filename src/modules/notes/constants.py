"""Constants of the ``notes`` module — code length, prefix and field sizes.

A single source for the ORM model (``String(n)``), the CRUD (``text.fit``) and the HTTP bodies.
The migration writes the numbers out as of its date; agreement is guarded by the tests comparing
the models with the schema. Were the sizes to drift apart, the mismatch would surface only on
PostgreSQL: SQLite does not check ``VARCHAR`` width at all.

``CODE_LEN`` is a contract NOT of this module alone: the consumers' link tables keep a
``note_code`` of this width.
"""

from __future__ import annotations

# The database holds the bare hex code; the type word is added on output and stripped on input
# (``notes.codes``).
NOTE_CODE_PREFIX = "NOTE"

# The same width as every other entity's code: a note code lands in the consumers' tables next to
# theirs, and two widths for one kind of reference is a truncation waiting to happen.
CODE_LEN = 10

# Over any of these is refused with the numbers, never cut (``text.fit``): the end of a document
# is where its point or its file list sits, and a silent cut takes exactly that.
TITLE_MAX = 128
# What the document is about and when to open it — the line a reader decides by.
DESCRIPTION_MAX = 512
# A document with sections, tables and diagrams, not a field of a form.
BODY_MAX = 65536


__all__ = ["BODY_MAX", "CODE_LEN", "DESCRIPTION_MAX", "NOTE_CODE_PREFIX", "TITLE_MAX"]
