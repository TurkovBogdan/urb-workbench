"""The base of a content handler — how an agent edits one content field of one entity over MCP.

A content field is a long markdown text the work lives in: a task's brief lists and its work
(``context``, ``constraints``, ``criteria``, ``plan``, ``progress``, ``result``), a stage's
``body``, a journal entry's ``body``. Every one of them is edited by the same four actions, and
every one of them has rules of its own — a cap, and whatever its entity's state forbids. So a
field is a class: the actions and the string work live here, once; a subclass names its field and
adds its own checks.

The actions are pure transforms over a string, applied in one write: load the row, check it, run
the transform, check the result, write. Every check runs BEFORE the write — a refusal leaves the
row exactly as it was, and the agent that reads "refused" is told the truth.

What travels back is not the text but the **seam**: a window on both sides of the edit, with the
inserted text replaced by a placeholder. The agent sent the text; what it needs back is exactly
what it does not know — how the insertion landed.

**The limit refuses rather than truncates,** and the refusal names the length of the RESULT. The
agent appended two lines to a nearly full field, and it is not those lines that hit the limit:
tell it the length of the piece it sent and it will cut in the wrong place.

A heading is looked for only outside fenced code: a ``# comment`` line inside a ```` ``` ````
block is not a heading, otherwise a section with a code example would be cut off in the middle of
the fence.

These handlers are the MCP surface's own: the HTTP API and CRUD write the same columns by their
own rules and do not go through here.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Sequence
from typing import ClassVar, NamedTuple, TypeVar

from src.core.database import write_scope
from src.modules.tasks.codes import strip_prefix, tagged
from src.modules.tasks.constants import TASK_CODE_PREFIX
from src.modules.tasks.models.task import TasksTask

PREVIEW_WINDOW_CHARS = 128
SEAM_TEXT_PLACEHOLDER = "<text>"
SEAM_TRUNCATION_MARK = "…"
PREVIEW_ELISION_MARK = " … "
HEADING_PATH_SEPARATOR = " > "

REPLACE_MODES = ("single", "all")
ADD_POSITIONS = ("start", "end", "before", "after")


# ── seams ─────────────────────────────────────────────────────────────────────
def _seam(before: str, after: str) -> str:
    """The edit's seam: ``PREVIEW_WINDOW_CHARS`` chars on each side, the text as a placeholder.

    ``…`` goes only where the window cuts through the middle of the text: the edge is already
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


# ── string transforms ─────────────────────────────────────────────────────────
def _searchable(find: str) -> str:
    """An empty string occurs everywhere and never ends: walking its occurrences would not stop."""
    if not find:
        raise ValueError("The text to look for must not be empty.")
    return find


def _append(current: str, *, text: str, position: str) -> tuple[str, str]:
    if position == "start":
        return text + current, _seam("", current)
    return current + text, _seam(current, "")


def _insert(current: str, *, text: str, anchor: str, position: str) -> tuple[str, str]:
    count = current.count(_searchable(anchor))
    if count == 0:
        raise ValueError(f"Anchor {anchor!r} not found in the text.")
    if count > 1:
        raise ValueError(f"Anchor {anchor!r} occurs {count} times — it must be unique.")
    at = current.index(anchor)
    cut = at if position == "before" else at + len(anchor)
    return current[:cut] + text + current[cut:], _seam(current[:cut], current[cut:])


def _replacement_seams(current: str, *, find: str) -> list[str]:
    """Seams of every occurrence in document order, each a window over the ORIGINAL text."""
    seams, at = [], current.find(find)
    while at != -1:
        seams.append(_seam(current[:at], current[at + len(find):]))
        at = current.find(find, at + len(find))
    return seams


def _replace_one(current: str, *, find: str, text: str) -> tuple[str, list[str]]:
    count = current.count(_searchable(find))
    if count == 0:
        raise ValueError(f"{find!r} is not in the text.")
    if count > 1:
        raise ValueError(
            f"{find!r} occurs {count} times — it must be unique to replace one. Pass a longer "
            "fragment, or mode='all' to replace every one."
        )
    return current.replace(find, text, 1), _replacement_seams(current, find=find)


def _replace_all(current: str, *, find: str, text: str) -> tuple[str, list[str]]:
    seams = _replacement_seams(current, find=_searchable(find))
    if not seams:
        raise ValueError(f"{find!r} is not in the text.")
    return current.replace(find, text), seams


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
    where = f"inside {resolved[-1]!r}" if resolved else "in the text"
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

    The boundary is computed here from the heading level, so what the agent cannot predict is
    exactly the extent of the cut: the seam around the new text would look just as neat with a
    cut twice as wide as intended.
    """

    removed: str
    removed_length: int
    stopped_at: str | None


def _set_section(current: str, *, heading: str, text: str) -> tuple[str, SectionCut]:
    """Replace a section (from its heading to the next of equal or higher level) with ``text``."""
    lines = current.split("\n")
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


# ── the handler ───────────────────────────────────────────────────────────────
Report = TypeVar("Report")


class McpContentHandler:
    """One content field of one entity type, as an MCP agent edits it.

    A subclass names the field — ``prefix`` and ``field`` are its key in the registry, ``model``
    and the column (``field``) are where it lives, ``limit`` its cap — and overrides ``check`` /
    ``validate`` for rules of its own. ``what`` names the field in refusals, ``overflow_hint``
    says what to do when it is full.
    """

    prefix: ClassVar[str]
    field: ClassVar[str]
    model: ClassVar[type]
    limit: ClassVar[int]
    what: ClassVar[str]
    overflow_hint: ClassVar[str] = "Shorten what is already there."

    # ── actions ───────────────────────────────────────────────────────────────
    async def set(self, code: str, *, text: str) -> int:
        """Replace the whole field; the answer is the new length."""
        await self._apply(code, lambda current: (text, None))
        return len(text)

    async def replace(self, code: str, *, find: str, text: str, mode: str) -> list[str]:
        """Replace ``find`` — exactly one occurrence, or every one; a seam per occurrence."""
        if mode not in REPLACE_MODES:
            raise ValueError(f"mode must be {' or '.join(map(repr, REPLACE_MODES))}.")
        transform = _replace_one if mode == "single" else _replace_all
        return await self._apply(code, lambda current: transform(current, find=find, text=text))

    async def set_section(self, code: str, *, heading: str, text: str) -> SectionCut:
        """Replace one heading section; the answer is what was cut."""
        return await self._apply(
            code, lambda current: _set_section(current, heading=heading, text=text)
        )

    async def add(self, code: str, *, text: str, position: str, anchor: str | None) -> str:
        """Add at the start or the end, or before / after a unique anchor; the answer is a seam."""
        if position not in ADD_POSITIONS:
            raise ValueError(f"position must be one of {', '.join(map(repr, ADD_POSITIONS))}.")
        if position in ("start", "end"):
            return await self._apply(
                code, lambda current: _append(current, text=text, position=position)
            )
        if anchor is None:
            raise ValueError(
                "position 'before'/'after' needs an anchor — the unique string to insert "
                "relative to. For the whole text use 'start' or 'end'."
            )
        return await self._apply(
            code,
            lambda current: _insert(current, text=text, anchor=anchor, position=position),
        )

    # ── rules — a field overrides what is its own ─────────────────────────────
    def task_code_of(self, row) -> str:
        """The task the row belongs to: a stage and a journal entry carry it in ``task_code``."""
        return row.task_code

    def check(self, row, task: TasksTask, code: str) -> None:
        """May the field be edited now. A deleted task is the person's to restore, not to edit."""
        if task.deleted_at is not None:
            raise ValueError(
                f"{tagged(TASK_CODE_PREFIX, task.code)} is deleted — editing it is closed until "
                "a person restores it. Say so rather than creating a replacement."
            )

    def validate(self, row, text: str, code: str) -> None:
        """Is the edited text acceptable. The cap refuses and names the RESULT's length.

        U+0000 is refused first: PostgreSQL cannot store it in text and fails the write with an
        encoding error, while SQLite keeps it — the same edit would pass in dev and break in
        production.
        """
        if "\x00" in text:
            raise ValueError(
                f"The text for {self.what} of {code} contains a NUL character (U+0000), which "
                "the database cannot store. Remove it and send again."
            )
        if len(text) > self.limit:
            raise ValueError(
                f"This would make {self.what} of {code} {len(text)} characters long, and the "
                f"limit is {self.limit} — {len(text) - self.limit} too many. The limit refuses "
                f"instead of trimming. {self.overflow_hint}"
            )

    # ── applying ──────────────────────────────────────────────────────────────
    async def _apply(self, code: str, edit: Callable[[str], tuple[str, Report]]) -> Report:
        """Load, check, transform, validate, write — nothing is written unless all of it passed."""
        async with write_scope() as s:
            row = await s.get(self.model, strip_prefix(code))
            if row is None:
                raise ValueError(f"{code} does not exist.")
            task = row if isinstance(row, TasksTask) else await s.get(
                TasksTask, self.task_code_of(row)
            )
            self.check(row, task, code)
            text, report = edit(getattr(row, self.field) or "")
            self.validate(row, text, code)
            setattr(row, self.field, text)
            await s.flush()
        return report


__all__ = [
    "ADD_POSITIONS",
    "HEADING_PATH_SEPARATOR",
    "PREVIEW_ELISION_MARK",
    "PREVIEW_WINDOW_CHARS",
    "REPLACE_MODES",
    "SEAM_TEXT_PLACEHOLDER",
    "SEAM_TRUNCATION_MARK",
    "McpContentHandler",
    "SectionCut",
]
