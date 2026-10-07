"""Body editor — edits to an entity's markdown text, dispatched by its code prefix.

Three entities in the module have a body, and in all of them it has the same name — the
``body`` column: for a task it is the plan, for a stage the description of the work, for a
journal entry its subject. One name across the module means one set of editing tools; the task
brief (``context`` and its neighbours) does not count as a body and is edited through the card.

The transforms are pure functions over a string; an input error (not found, ambiguous) →
``ValueError``. What travels back is not the body but the **seam**: a window on both sides of
the edit, with the inserted text itself replaced by a placeholder. The agent sent the text; what
it needs back is exactly what it does not know — how the insertion landed.

Two rules here are our own; the neighbouring server does not have them.

**The limit refuses rather than truncates,** and the refusal names the length of the RESULT. The
agent appended two lines to a nearly full body, and it is not those lines that hit the limit:
tell it the length of the piece it sent and it will cut in the wrong place.

**The body of a started stage is not edited.** The plan ahead is alive, the plan behind is
frozen: otherwise the wording gets fitted to the outcome, and the "promised one thing, did
another" gap disappears together with the only signal the plan is kept for. The ban does not
apply to the task plan or to a journal entry's subject — the first lives as long as the task
does, and in the second the agent is still working things out.

A heading is looked for only outside fenced code: a ``# comment`` line inside a
```` ``` ```` block is not a heading, otherwise a section with a code example would be cut off
in the middle of the fence.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Sequence
from typing import NamedTuple, TypeVar

from src.core.database import write_scope
from src.modules.tasks.codes import code_prefix, strip_prefix
from src.modules.tasks.constants import (
    BODY_MAX,
    NOTE_BODY_MAX,
    NOTE_CODE_PREFIX,
    STAGE_CODE_PREFIX,
    TASK_CODE_PREFIX,
    TASK_STATUSES_TERMINAL,
    STATUS_PLANNED,
)
from src.modules.tasks.models.note import TasksNote
from src.modules.tasks.models.stage import TasksStage
from src.modules.tasks.models.task import TasksTask


class _Holder(NamedTuple):
    """What is known about this type's body: the model, the cap, and how to name it to the agent."""

    model: type
    limit: int
    what: str


_HOLDERS = {
    TASK_CODE_PREFIX: _Holder(TasksTask, BODY_MAX, "the task plan"),
    STAGE_CODE_PREFIX: _Holder(TasksStage, BODY_MAX, "the stage body"),
    NOTE_CODE_PREFIX: _Holder(TasksNote, NOTE_BODY_MAX, "the journal entry body"),
}

PREVIEW_WINDOW_CHARS = 128
SEAM_TEXT_PLACEHOLDER = "<text>"
SEAM_TRUNCATION_MARK = "…"
PREVIEW_ELISION_MARK = " … "
HEADING_PATH_SEPARATOR = " > "


def _holder_for(code: str) -> _Holder:
    holder = _HOLDERS.get(code_prefix(code))
    if holder is None:
        raise ValueError(
            f"{code!r} has no body to edit — pass a "
            f"{' / '.join(f'{p}@' for p in _HOLDERS)} code. The brief of a task "
            "(goal, context, constraints, criteria) is not a body: it is edited with "
            "task_update."
        )
    return holder


def _seam(before: str, after: str) -> str:
    """The edit's seam: ``PREVIEW_WINDOW_CHARS`` chars on each side, the text as a placeholder.

    ``…`` goes only where the window cuts through the middle of the body: the edge is already
    visible from the window ending, and if the two cases looked the same, the reader would have
    to guess.
    """
    head, tail = before[-PREVIEW_WINDOW_CHARS:], after[:PREVIEW_WINDOW_CHARS]
    opening = SEAM_TRUNCATION_MARK if len(before) > PREVIEW_WINDOW_CHARS else ""
    closing = SEAM_TRUNCATION_MARK if len(after) > PREVIEW_WINDOW_CHARS else ""
    return f"{opening}{head}{SEAM_TEXT_PLACEHOLDER}{tail}{closing}"


def _elided(text: str) -> str:
    """A fragment preview: head and tail joined by an elision mark; a short one is shown whole."""
    if len(text) <= PREVIEW_WINDOW_CHARS * 2:
        return text
    return f"{text[:PREVIEW_WINDOW_CHARS]}{PREVIEW_ELISION_MARK}{text[-PREVIEW_WINDOW_CHARS:]}"


# ── pure transforms ───────────────────────────────────────────────────────────
def op_set(body: str, *, text: str) -> str:
    return text


def op_append(body: str, *, text: str, position: str) -> tuple[str, str]:
    if position == "start":
        return text + body, _seam("", body)
    if position == "end":
        return body + text, _seam(body, "")
    raise ValueError("position must be 'start' or 'end'.")


def op_insert(body: str, *, text: str, anchor: str, position: str) -> tuple[str, str]:
    count = body.count(_searchable(anchor))
    if count == 0:
        raise ValueError(f"Anchor {anchor!r} not found in the body.")
    if count > 1:
        raise ValueError(f"Anchor {anchor!r} occurs {count} times — it must be unique.")
    at = body.index(anchor)
    cut = at if position == "before" else at + len(anchor)
    if position not in ("before", "after"):
        raise ValueError("position must be 'before' or 'after'.")
    return body[:cut] + text + body[cut:], _seam(body[:cut], body[cut:])


def _searchable(find: str) -> str:
    """An empty string occurs everywhere and never ends: walking its occurrences would not stop."""
    if not find:
        raise ValueError("The text to look for must not be empty.")
    return find


def _replacement_seams(body: str, *, find: str) -> list[str]:
    """Seams of every occurrence in document order, each a window over the ORIGINAL body."""
    seams, at = [], body.find(find)
    while at != -1:
        seams.append(_seam(body[:at], body[at + len(find):]))
        at = body.find(find, at + len(find))
    return seams


def op_replace(body: str, *, find: str, text: str) -> tuple[str, list[str]]:
    count = body.count(_searchable(find))
    if count == 0:
        raise ValueError(f"{find!r} is not in the body.")
    if count > 1:
        raise ValueError(
            f"{find!r} occurs {count} times — it must be unique to replace one. Pass a longer "
            "fragment, or mode='all' to replace every one."
        )
    return body.replace(find, text, 1), _replacement_seams(body, find=find)


def op_replace_all(body: str, *, find: str, text: str) -> tuple[str, list[str]]:
    seams = _replacement_seams(body, find=_searchable(find))
    if not seams:
        raise ValueError(f"{find!r} is not in the body.")
    return body.replace(find, text), seams


# ── heading parsing ───────────────────────────────────────────────────────────
_FENCE_LINE = re.compile(r"^\s*(?P<marker>`{3,}|~{3,})(?P<info>.*)$")


def _heading_level(line: str) -> int:
    """The markdown heading level (number of leading ``#``), or 0 if the line is not a heading."""
    stripped = line.lstrip()
    hashes = len(stripped) - len(stripped.lstrip("#"))
    if hashes == 0:
        return 0
    return hashes if len(stripped) == hashes or stripped[hashes] == " " else 0


def _heading_levels(lines: Sequence[str]) -> list[int]:
    """A level for every line; 0 means not a heading, including lines inside fenced code."""
    levels, opened = [], ""
    for line in lines:
        fence = _FENCE_LINE.match(line)
        if opened:
            if fence and fence["marker"][0] == opened[0] and len(fence["marker"]) >= len(
                opened
            ) and not fence["info"].strip():
                opened = ""
            levels.append(0)
        elif fence:
            opened = fence["marker"]
            levels.append(0)
        else:
            levels.append(_heading_level(line))
    return levels


class _Scope(NamedTuple):
    start: int
    limit: int


def _block_end(levels: Sequence[int], start: int, limit: int) -> int:
    """Where a heading's block ends: the next heading of the same or a higher level."""
    level = levels[start]
    for index in range(start + 1, limit):
        if levels[index] and levels[index] <= level:
            return index
    return limit


def _matches(lines, levels, segment: str, scope: _Scope) -> list[int]:
    return [
        index
        for index in range(scope.start, scope.limit)
        if levels[index] and lines[index].strip() == segment
    ]


def _segment_index(lines, levels, segment: str, scope: _Scope, resolved: Sequence[str]) -> int:
    """The single line of the segment within the scope; zero or two matches are refused.

    Ambiguity is a refusal, not the first match: a silently taken first section would rewrite a
    section other than the one the agent had in mind, and there would be no way to find out.
    """
    if _heading_level(segment) == 0:
        raise ValueError(
            f"{segment!r} is not a markdown heading — every segment carries its own '#', "
            f"e.g. '## Section{HEADING_PATH_SEPARATOR}### Subsection'."
        )
    found = _matches(lines, levels, segment, scope)
    where = f"inside {resolved[-1]!r}" if resolved else "in the body"
    if not found:
        raise ValueError(f"Heading {segment!r} is not {where}.")
    if len(found) > 1:
        raise ValueError(
            f"Heading {segment!r} occurs {len(found)} times {where} — it must name exactly one "
            f"section. Say which with a path, segments separated by {HEADING_PATH_SEPARATOR!r}: "
            f"'## Section{HEADING_PATH_SEPARATOR}### Subsection'."
        )
    return found[0]


def _heading_index(lines, levels, heading: str) -> int:
    """The line of a heading named by a bare heading or by an ``A > B`` path."""
    segments = [segment.strip() for segment in heading.split(HEADING_PATH_SEPARATOR)]
    scope = _Scope(0, len(lines))
    index = _segment_index(lines, levels, segments[0], scope, resolved=[])
    for depth, segment in enumerate(segments[1:], start=1):
        scope = _Scope(index + 1, _block_end(levels, index, scope.limit))
        index = _segment_index(lines, levels, segment, scope, resolved=segments[:depth])
    return index


class SectionCut(NamedTuple):
    """What a section edit cut out: a block preview, its length, and the heading that ended it.

    The server computes the boundary from the heading level, so what the agent cannot predict is
    exactly the extent of the cut: the seam around the new text would look just as neat with a
    cut twice as wide as intended.
    """

    removed: str
    removed_length: int
    stopped_at: str | None


def op_set_section(body: str, *, heading: str, text: str) -> tuple[str, SectionCut]:
    """Replace a section (from its heading to the next of equal or higher level) with ``text``."""
    lines = body.split("\n")
    levels = _heading_levels(lines)
    start = _heading_index(lines, levels, heading)
    end = _block_end(levels, start, len(lines))
    removed = "\n".join(lines[start:end])
    cut = SectionCut(
        removed=_elided(removed),
        removed_length=len(removed),
        stopped_at=lines[end].strip() if end < len(lines) else None,
    )
    return "\n".join(lines[:start] + text.split("\n") + lines[end:]), cut


# ── applying ──────────────────────────────────────────────────────────────────
Report = TypeVar("Report")


def _fits(text: str, holder: _Holder, code: str) -> str:
    """The whole result, or a refusal naming ITS length, not the length of the piece sent."""
    if len(text) > holder.limit:
        raise ValueError(
            f"This would make {holder.what} of {code} {len(text)} characters long, and the "
            f"limit is {holder.limit} — {len(text) - holder.limit} too many. The limit refuses "
            "instead of trimming because the end of a plan is where the files are listed. "
            "Shorten what is already there; a plan's detail that does not fit belongs in "
            "stages (an extended task) or in a subtask."
        )
    return text


def _editable(row, code: str) -> None:
    """A started stage keeps its body — "the plan behind is frozen" as a gate, not a request."""
    if isinstance(row, TasksStage) and row.status != STATUS_PLANNED:
        gone = "finished" if row.status in TASK_STATUSES_TERMINAL else "running"
        raise ValueError(
            f"Stage {code} is already {gone}, and the plan behind you does not get rewritten — "
            "otherwise nobody can tell what was promised from what was done. Record the change "
            "with note_add(type='decision') and add the stage that follows it."
        )


async def apply_edit(
    code: str, edit: Callable[[str], tuple[str, Report]]
) -> tuple[object, Report]:
    """Apply ``edit(body) -> (new body, report)`` to the body of entity ``code`` (prefixed)."""
    holder = _holder_for(code)
    bare = strip_prefix(code)
    async with write_scope() as s:
        row = await s.get(holder.model, bare)
        if row is None:
            raise ValueError(f"{code} does not exist.")
        _editable(row, code)
        text, report = edit(row.body or "")
        row.body = _fits(text, holder, code)
        await s.flush()
        await s.refresh(row)
    return row, report


async def apply(code: str, mutate: Callable[[str], str]) -> object:
    """``apply_edit`` for an edit that has nothing to report about itself beyond the new body."""
    row, _ = await apply_edit(code, lambda body: (mutate(body), None))
    return row


__all__ = [
    "HEADING_PATH_SEPARATOR",
    "PREVIEW_ELISION_MARK",
    "PREVIEW_WINDOW_CHARS",
    "SEAM_TEXT_PLACEHOLDER",
    "SEAM_TRUNCATION_MARK",
    "SectionCut",
    "apply",
    "apply_edit",
    "op_append",
    "op_insert",
    "op_replace",
    "op_replace_all",
    "op_set",
    "op_set_section",
]
