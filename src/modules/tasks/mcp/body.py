"""MCP-тулы редактора тела — четыре правки одного и того же текста по коду сущности.

Тело есть у задачи (план), этапа (описание работы) и записи журнала (её предмет), и во всех
трёх это колонка ``body``. Постановка задачи телом не считается: у неё пять разных полей, и
``body_set(code, text)`` на них был бы неоднозначен.

Диспетч, лимиты и запрет на правку начатого этапа — в ``services/body.py``. Здесь только
описания и форма ответа.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from src.modules.tasks.codes import code_prefix, strip_prefix
from src.modules.tasks.dto import (
    AgentBodyAdded,
    AgentBodyReplaced,
    AgentBodySectionSet,
    AgentBodySet,
)
from src.modules.tasks.mcp.scope import require_scope
from src.modules.tasks.services import body as body_service

if TYPE_CHECKING:  # fork fastmcp — только backend (через mcp_server(ctx))
    from fastmcp import FastMCP


async def _fenced(code: str) -> str:
    """Провести код через забор пространства и вернуть его голую форму.

    Забор здесь нужен ровно так же, как везде: ``STAGE@`` чужой задачи резолвится до её
    пространства, и правка мимо контура становится отказом, а не тихой записью.
    """
    prefix = code_prefix(code)
    bare = strip_prefix(code) or ""
    if prefix:
        await require_scope(prefix, bare)
    return code


def register(mcp: "FastMCP") -> None:

    @mcp.tool()
    async def body_set(code: str, text: str) -> AgentBodySet:
        """Replace the whole body of a TASK@ (its plan), a STAGE@ or a NOTE@ with `text`.

        This is how a plan is first written: read the code, then say what you intend to do and
        which files it touches. Naming the files you read and the files you will change is what
        separates a plan from a promise.

        Returns a receipt only — the new length, since the body is the text you just sent. Watch
        it against the limit: going over is refused, not trimmed, because the end of a plan is
        where the file list lives. To amend part of a body, use body_replace / body_set_section
        / body_add instead of rewriting it whole.

        Args:
            code: Whose body to replace — a TASK@, STAGE@ or NOTE@ code. A task's brief (goal,
                context, constraints, criteria) is not a body: that is task_update.
            text: The new body — everything there now is discarded.
                Markdown, rendered in the interface — skill_get('markdown').
        """
        row = await body_service.apply(
            await _fenced(code), lambda body: body_service.op_set(body, text=text)
        )
        return AgentBodySet(code=code, length=len(row.body or ""))

    @mcp.tool()
    async def body_replace(
        code: str, find: str, text: str, mode: str = "single"
    ) -> AgentBodyReplaced:
        """Replace the exact string `find` with `text` in the body of a TASK@ / STAGE@ / NOTE@.

        - `single` (default) — `find` must occur exactly once, or the call fails saying how many
          times it occurs. Pass a longer fragment to single one out.
        - `all` — every occurrence. Absent in both modes is an error.

        Returns `edits`: one seam per occurrence in document order — 128 characters of the body
        either side of the edit, with `<text>` standing in for what you sent (`…` at an end marks
        a window cut short mid-body). Read it: it is where a splice goes wrong.

        Args:
            code: Whose body to edit — a TASK@, STAGE@ or NOTE@ code.
            find: The exact substring as it stands in the body.
            text: What replaces it.
                Markdown, rendered in the interface — skill_get('markdown').
            mode: single (exactly one occurrence) or all (every one).
        """
        if mode == "single":
            def edit(body: str):
                return body_service.op_replace(body, find=find, text=text)
        elif mode == "all":
            def edit(body: str):
                return body_service.op_replace_all(body, find=find, text=text)
        else:
            raise ValueError("mode must be 'single' or 'all'.")

        _, seams = await body_service.apply_edit(await _fenced(code), edit)
        return AgentBodyReplaced(code=code, replaced=len(seams), edits=seams)

    @mcp.tool()
    async def body_set_section(code: str, heading: str, text: str) -> AgentBodySectionSet:
        """Replace one heading section of a TASK@ / STAGE@ / NOTE@ body with `text`.

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
            code: Whose body to edit — a TASK@, STAGE@ or NOTE@ code.
            heading: The heading line, or the path to it when it repeats.
            text: The whole new section, normally starting with the heading again — leave it out
                and the heading goes too. Spliced in verbatim.
                Markdown, rendered in the interface — skill_get('markdown').
        """
        _, cut = await body_service.apply_edit(
            await _fenced(code),
            lambda body: body_service.op_set_section(body, heading=heading, text=text),
        )
        return AgentBodySectionSet(
            code=code,
            removed=cut.removed,
            removed_length=cut.removed_length,
            stopped_at=cut.stopped_at,
        )

    @mcp.tool()
    async def body_add(
        code: str, text: str, position: str, anchor: str | None = None
    ) -> AgentBodyAdded:
        """Add text to the body of a TASK@ / STAGE@ / NOTE@ entity.

        - `start` / `end` — prepend or append to the whole body. Appending to a plan is how a
          file you had not read yet gets into it.
        - `before` / `after` — insert relative to `anchor`, a heading or any unique string.

        Your text is spliced in verbatim: no newline and no blank line is added around it at any
        position. Carry the blank line you want at the start or end of `text` yourself, or the
        addition runs into the neighbouring paragraph.

        Returns the seam — 128 characters either side, with `<text>` standing in for what you
        sent. Read it: it shows exactly what your text ran into.

        Args:
            code: Whose body to add to — a TASK@, STAGE@ or NOTE@ code.
            text: What to add, carrying its own leading/trailing blank lines.
                Markdown, rendered in the interface — skill_get('markdown').
            position: start / end / before / after.
            anchor: The unique anchor string (required for before / after).
        """
        if position in ("start", "end"):
            def edit(body: str):
                return body_service.op_append(body, text=text, position=position)
        elif position in ("before", "after"):
            if anchor is None:
                raise ValueError(
                    "position 'before'/'after' needs an anchor — the unique string to insert "
                    "relative to. For the whole body use 'start' or 'end'."
                )

            def edit(body: str):
                return body_service.op_insert(
                    body, text=text, anchor=anchor, position=position
                )
        else:
            raise ValueError("position must be 'start', 'end', 'before' or 'after'.")

        _, seam = await body_service.apply_edit(await _fenced(code), edit)
        return AgentBodyAdded(code=code, edit=seam)


__all__ = ["register"]
