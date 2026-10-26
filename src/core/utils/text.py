"""Control characters in short texts: one rule for every surface that takes them.

PostgreSQL cannot store U+0000 at all — SQLite keeps it, so a check left to the database passes on
one provider and fails on the other, after the work is done. The rest of C0 and DEL are not text a
person reads: a single-line value (a name, a title) shows in a list, travels in a header and in an
answer to the agent, and a stray line break or bell there is either an injection or a mistake.
Prose (a description) keeps its line breaks and tabs — tab, line feed, carriage return.
"""

from __future__ import annotations

import re

_IN_A_LINE = re.compile(r"[\x00-\x1f\x7f]")
_IN_PROSE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


def control_character(value: str | None, *, prose: bool = False) -> str | None:
    """The first control character of ``value`` as ``U+XXXX``; ``None`` — there is none.

    ``prose`` — the value may span lines: tab, line feed and carriage return are text there.
    """
    if not value:
        return None
    found = (_IN_PROSE if prose else _IN_A_LINE).search(value)
    return None if found is None else f"U+{ord(found.group()):04X}"


__all__ = ["control_character"]
