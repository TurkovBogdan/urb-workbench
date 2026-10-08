"""The content tools — four edits of any content field, addressed by entity code and field name.

Which field of which entity, and by what rules, is the registry's business (``registry.py``): a
tool fences the code into the session's workspace, takes the field's handler and runs one action
of it. Only the descriptions and the reply shape are here.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from src.modules.tasks.codes import code_prefix, strip_prefix, tagged
from src.modules.tasks.dto import (
    AgentContentAdded,
    AgentContentReplaced,
    AgentContentSectionSet,
    AgentContentSet,
)
from src.modules.tasks.mcp.content.base import McpContentHandler
from src.modules.tasks.mcp.content.registry import handler_for
from src.modules.tasks.mcp.scope import require_scope

if TYPE_CHECKING:  # fastmcp fork — backend only (via mcp_server(ctx))
    from fastmcp import FastMCP


async def _target(code: str, field: str) -> tuple[str, McpContentHandler]:
    """The canonical code inside the workspace fence, and the handler of its field.

    The handler is found first: a code of a type with no content is refused for what it is, not
    for where it lives. The fence then works as everywhere else — a ``STAGE@`` of another
    workspace's task is refused rather than silently written.

    Canonical, not as sent: every tool here echoes the code in its answer, and a code sent in
    lower case must come back the way every other tool returns it — upper case.
    """
    handler = handler_for(code, field)
    prefix = code_prefix(code)
    bare = strip_prefix(code) or ""
    await require_scope(prefix, bare)
    return tagged(prefix, bare), handler


def register(mcp: "FastMCP") -> None:

    @mcp.tool()
    async def content_set(code: str, field: str, text: str) -> AgentContentSet:
        """Replace a content field of a TASK@, a STAGE@ or a NOTE@ with `text`, whole.

        This is how a field is first written — a plan after reading the code, a result at
        hand-over. Naming the files you read and the files you will change is what separates a
        plan from a promise.

        Returns a receipt only — the new length, since the field is the text you just sent.
        Watch it against the limit: going over is refused, not trimmed. To amend part of a
        field, use content_replace / content_set_section / content_add instead of rewriting it.

        A `simple` task has only its context: constraints, criteria, plan, progress and result
        are refused there by every content tool until the type is raised with task_update.

        Args:
            code: Whose field to replace — a TASK@, STAGE@ or NOTE@ code.
            field: The field, by the name the answers show it under. TASK@: context,
                constraints, criteria, plan, progress, result. STAGE@ and NOTE@: body.
            text: The new text — everything there now is discarded.
                Markdown, rendered in the interface — skill_get('markdown').
        """
        canonical, handler = await _target(code, field)
        length = await handler.set(canonical, text=text)
        return AgentContentSet(code=canonical, field=field, length=length)

    @mcp.tool()
    async def content_replace(
        code: str, field: str, find: str, text: str, mode: str = "single"
    ) -> AgentContentReplaced:
        """Replace the exact string `find` with `text` in a content field.

        - `single` (default) — `find` must occur exactly once, or the call fails saying how many
          times it occurs. Pass a longer fragment to single one out.
        - `all` — every occurrence. Absent in both modes is an error.

        Returns `edits`: one seam per occurrence in document order — 128 characters of the field
        either side of the edit, with `<text>` standing in for what you sent (`…` at an end marks
        a window cut short mid-text). Read it: it is where a splice goes wrong.

        Args:
            code: Whose field to edit — a TASK@, STAGE@ or NOTE@ code.
            field: TASK@: context, constraints, criteria, plan, progress, result.
                STAGE@ and NOTE@: body.
            find: The exact substring as it stands in the field.
            text: What replaces it.
                Markdown, rendered in the interface — skill_get('markdown').
            mode: single (exactly one occurrence) or all (every one).
        """
        canonical, handler = await _target(code, field)
        seams = await handler.replace(canonical, find=find, text=text, mode=mode)
        return AgentContentReplaced(
            code=canonical, field=field, replaced=len(seams), edits=seams
        )

    @mcp.tool()
    async def content_set_section(
        code: str, field: str, heading: str, text: str
    ) -> AgentContentSectionSet:
        """Replace one heading section of a content field with `text`.

        The section runs from its heading line down to the next heading of equal or higher
        level, so it takes its own subsections with it. A `#` line inside a ``` or ~~~ fence is
        code, not a heading, and never ends a section.

        `heading` matches the heading line as a whole, level included, and must occur exactly
        once; one that repeats is refused. Say which you mean with a path — `## Plan > ### Risks`
        — every segment carrying its own `#`.

        Returns what was CUT, not what you wrote: the boundary is computed here, so the reach of
        the cut is the one thing you cannot predict. A section you thought was 500 characters
        coming back as 4000 is a cut that ran past it — and the preview is all there is, the cut
        text is stored nowhere.

        Args:
            code: Whose field to edit — a TASK@, STAGE@ or NOTE@ code.
            field: TASK@: context, constraints, criteria, plan, progress, result.
                STAGE@ and NOTE@: body.
            heading: The heading line, or the path to it when it repeats.
            text: The whole new section, normally starting with the heading again — leave it out
                and the heading goes too. Spliced in verbatim.
                Markdown, rendered in the interface — skill_get('markdown').
        """
        canonical, handler = await _target(code, field)
        cut = await handler.set_section(canonical, heading=heading, text=text)
        return AgentContentSectionSet(
            code=canonical,
            field=field,
            removed=cut.removed,
            removed_length=cut.removed_length,
            stopped_at=cut.stopped_at,
        )

    @mcp.tool()
    async def content_add(
        code: str, field: str, text: str, position: str, anchor: str | None = None
    ) -> AgentContentAdded:
        """Add text to a content field — at an end, or next to an anchor.

        - `start` / `end` — prepend or append to the whole field. Appending is how a progress
          entry is written, and how a file you had not read yet gets into a plan.
        - `before` / `after` — insert relative to `anchor`, a heading or any unique string.

        Your text is spliced in verbatim: no newline and no blank line is added around it at any
        position. Carry the blank line you want at the start or end of `text` yourself, or the
        addition runs into the neighbouring paragraph.

        Returns the seam — 128 characters either side, with `<text>` standing in for what you
        sent. Read it: it shows exactly what your text ran into.

        Args:
            code: Whose field to add to — a TASK@, STAGE@ or NOTE@ code.
            field: TASK@: context, constraints, criteria, plan, progress, result.
                STAGE@ and NOTE@: body.
            text: What to add, carrying its own leading/trailing blank lines.
                Markdown, rendered in the interface — skill_get('markdown').
            position: start / end / before / after.
            anchor: The unique anchor string (required for before / after).
        """
        canonical, handler = await _target(code, field)
        seam = await handler.add(canonical, text=text, position=position, anchor=anchor)
        return AgentContentAdded(code=canonical, field=field, edit=seam)


__all__ = ["register"]
