"""The executor: split the codes by prefix, ask each type's handler once, answer every code.

One call per type, whatever the number of codes: the handler reads its rows in a batch, so ten
pills of one body cost what one does.

Every requested code gets a record, in the order it was asked, duplicates folded:

- a code of the wrong shape, or of a prefix nobody registered — ``not_found``, before any handler;
- a code its handler gave no answer for — ``failed``, and the log says which handler skipped it;
- a handler that raised — ``failed`` for every code it was asked about, the traceback logged.

The handler's own verdicts (``not_found`` / ``foreign_scope`` / ``deleted``) pass through as they
are: whether a code belongs to the workspace is the type's knowledge, not the executor's.
"""

from __future__ import annotations

import re
from collections.abc import Iterable

from src.core.loggers import get_logger
from src.modules.core_lookup.dto import PreviewErrorOut, PreviewOut
from src.modules.core_lookup.registry import (
    Filters,
    LookupType,
    Miss,
    Preview,
    PreviewResult,
    type_for,
)

_LOG = get_logger("core_lookup")

_CODE = re.compile(r"^([A-Z]+)@([0-9A-F]+)$")

MISS_MESSAGES = {
    Miss.NOT_FOUND: "No such entity.",
    Miss.FOREIGN_SCOPE: "The entity belongs to another workspace.",
    Miss.DELETED: "The entity is deleted.",
    Miss.FAILED: "The preview could not be loaded.",
}


async def preview(codes: Iterable[str], filters: Filters) -> list[PreviewOut]:
    """A record for every distinct code, in request order."""
    wanted = list(dict.fromkeys(code.strip().upper() for code in codes))
    answers: dict[str, Preview | Miss] = {}
    asked: dict[LookupType, list[tuple[str, str]]] = {}
    for code in wanted:
        match = _CODE.match(code)
        kind = type_for(match[1]) if match else None
        if match is None or kind is None:
            answers[code] = Miss.NOT_FOUND
            continue
        asked.setdefault(kind, []).append((code, match[2]))
    for kind, pairs in asked.items():
        result = await _ask(kind, [bare for _, bare in pairs], filters)
        for code, bare in pairs:
            answer = result.get(bare)
            if answer is None:
                _LOG.error("lookup: the %s@ handler gave no answer for %s", kind.prefix, code)
                answer = Miss.FAILED
            answers[code] = answer
    return [_record(code, answers[code]) for code in wanted]


async def _ask(kind: LookupType, bare_codes: list[str], filters: Filters) -> PreviewResult:
    try:
        return await kind.preview(list(dict.fromkeys(bare_codes)), filters)
    except Exception:
        _LOG.exception("lookup: the %s@ handler failed on %d codes", kind.prefix, len(bare_codes))
        return {}


def _record(code: str, answer: Preview | Miss) -> PreviewOut:
    if isinstance(answer, Miss):
        return PreviewOut(code=code, error=PreviewErrorOut(code=answer, message=MISS_MESSAGES[answer]))
    return PreviewOut(
        code=code, title=answer.title, description=answer.description, link=answer.link
    )


__all__ = ["MISS_MESSAGES", "preview"]
