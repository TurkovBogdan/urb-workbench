"""Content field of a codex note: its ``body``.

The handler serves the whole ``CODEX@`` prefix — a codex and a note share it — and a codex code is
refused: a codex's rules are the person's. A note is written only through a mount that lets the
agent write (``entities/codex.py``); the check reads the active workspace inside the edit.
``title``, ``description`` and ``slug`` are not content — ``codex_update`` sets them.
"""

from __future__ import annotations

from src.modules.codex.constants import BODY_MAX
from src.modules.codex.models import Codex, CodexNote
from src.modules.workbench import session
from src.modules.workbench.content.base import McpContentHandler
from src.modules.workbench.entities.codex import (
    CodexFence,
    codex_is_the_persons,
    require_writable_codex,
)


class McpCodexNoteBodyHandler(CodexFence, McpContentHandler):
    field = "body"
    limit = BODY_MAX
    what = "the codex note body"
    overflow_hint = "A note past this size is two notes: split it with codex_add."

    async def load(self, s, bare: str):
        if await s.get(Codex, bare) is not None:
            raise ValueError(codex_is_the_persons(bare))
        return await s.get(CodexNote, bare)

    async def check_row(self, s, row, code: str) -> None:
        if row.deleted_at is not None:
            raise ValueError(f"{code} is deleted — a person restores it, then it can be edited.")
        await require_writable_codex(row.codex_code, await session.require_active())


__all__ = ["McpCodexNoteBodyHandler"]
