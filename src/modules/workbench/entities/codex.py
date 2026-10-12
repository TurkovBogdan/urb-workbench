"""``CODEX@`` on the agent surface: one prefix over two tables, visible through mounts.

A codex and a codex note share the prefix, so one handler serves both and finds the row itself
(``contracts`` explains why a handler, not the tool, knows where the row is). Visibility is not
ownership: a codex belongs to no workspace and is mounted into several, so "visible here" means
"its codex is mounted into the active workspace" — not ``OwnedFence``.

**Writing** is the agent's only on notes, and only through a mount that allows it
(``codex.rules.agent_may_write``). The codex itself — its title, segment and rules — is the
person's: every write tool refuses a codex code and says so.
"""

from __future__ import annotations

from src.modules.codex.codes import tagged
from src.modules.codex.constants import CODEX_CODE_PREFIX
from src.modules.codex.crud import codex as codex_crud
from src.modules.codex.crud import mount as mount_crud
from src.modules.codex.crud import note as note_crud
from src.modules.codex.models import Codex, CodexNote
from src.modules.codex.rules import agent_may_write
from src.modules.workbench import session
from src.modules.workbench.contracts import Deletable, Fence, Openable
from src.modules.workspace.models.workspace import Workspace


def code_of(bare: str) -> str:
    return str(tagged(CODEX_CODE_PREFIX, bare))


async def codex_of(bare: str) -> str | None:
    """The codex a ``CODEX@`` code belongs to — itself for a codex; ``None`` — no such code."""
    if await codex_crud.codex_get(bare, include_deleted=True) is not None:
        return bare
    note = await note_crud.note_get(bare, include_deleted=True)
    return note.codex_code if note else None


def codex_is_the_persons(bare: str) -> str:
    return (
        f"{code_of(bare)} is a codex, not a note — a codex (its title, segment and rules) is "
        "edited by the person in the interface. You write the notes inside it."
    )


async def require_writable_note(bare: str, active: Workspace) -> CodexNote:
    """A live note of a codex mounted here with the agent's right to write — or the refusal."""
    if await codex_crud.codex_get(bare, include_deleted=True) is not None:
        raise ValueError(codex_is_the_persons(bare))
    note = await note_crud.note_get(bare)
    if note is None:
        raise ValueError(f"{code_of(bare)} does not exist (or is deleted).")
    await require_writable_codex(note.codex_code, active)
    return note


async def require_writable_codex(codex_code: str, active: Workspace) -> Codex:
    codex = await codex_crud.codex_get(codex_code)
    mount = await mount_crud.mount_get(codex_code, active.code)
    if codex is None or mount is None:
        raise ValueError(not_mounted(codex_code, active))
    if not agent_may_write(mount):
        named = f"{'/' + codex.segment!r} ({code_of(codex.code)})"
        raise ValueError(
            f"The codex {named} is not editable for you in {active.title!r} — writing is "
            f"switched off in its mount. Tell the user the codex {named} is read-only for you "
            "and what you wanted to change."
        )
    return codex


def not_mounted(bare: str, active: Workspace) -> str:
    return (
        f"{code_of(bare)} is not in a codex mounted into {active.title!r}. Only mounted codexes "
        "are visible here — codex_index lists them; mounting is the person's."
    )


class CodexFence(Fence):
    prefix = CODEX_CODE_PREFIX

    async def require_visible(self, bare: str, active: Workspace) -> None:
        codex_code = await codex_of(bare)
        if codex_code is None:
            return
        if await mount_crud.mount_get(codex_code, active.code) is None:
            raise ValueError(not_mounted(bare, active))


class CodexPage(CodexFence, Openable):
    async def page(self, bare: str) -> str:
        """The codex materials, opened on this node — one address for a codex and a note alike
        (`web/src/features/codex/paths.ts`)."""
        if await codex_of(bare) is None:
            raise ValueError(f"{code_of(bare)} does not exist (or is deleted) — no page to show.")
        return f"/codex/materials/{code_of(bare)}"


class CodexDeletion(CodexFence, Deletable):
    async def delete(self, bare: str) -> bool:
        """A note, to the bin, alone — one with live children is refused with their list."""
        active = await session.require_active()
        await require_writable_note(bare, active)
        try:
            return await note_crud.note_delete(bare)
        except note_crud.NoteHasChildren as error:
            listed = ", ".join(
                f"{code_of(code)} ({segment})" for code, segment in error.children
            )
            raise ValueError(
                f"{code_of(bare)} has live child notes: {listed}. Delete them first, one by one; "
                "removing a whole branch at once is the person's."
            ) from error


__all__ = [
    "CodexDeletion",
    "CodexFence",
    "CodexPage",
    "code_of",
    "codex_is_the_persons",
    "codex_of",
    "not_mounted",
    "require_writable_codex",
    "require_writable_note",
]
