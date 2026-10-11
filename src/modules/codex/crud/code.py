"""A fresh ``CODEX@`` code — free in both tables that share the prefix.

A codex and a codex note are found by one code, so a note drawing the code of a codex would make
one of them unreachable, and neither table's primary key would notice. The draw is checked
against both inside the writer's transaction; a collision at 40 bits is rare enough that a retry
loop costs nothing, and it is bounded so a broken generator fails loudly instead of spinning.
"""

from __future__ import annotations

from sqlalchemy import exists, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.modules.codex.codes import new_code
from src.modules.codex.models import Codex, CodexNote

_ATTEMPTS = 8


async def codex_new_code(session: AsyncSession) -> str:
    """A code taken by no codex and no codex note, deleted rows included."""
    for _ in range(_ATTEMPTS):
        code = new_code()
        taken = await session.scalar(
            select(
                or_(
                    exists().where(Codex.code == code),
                    exists().where(CodexNote.code == code),
                )
            )
        )
        if not taken:
            return code
    raise RuntimeError(f"No free CODEX@ code after {_ATTEMPTS} draws — the generator is broken.")


__all__ = ["codex_new_code"]
