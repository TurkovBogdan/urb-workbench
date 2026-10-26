"""``FILE@`` on the agent surface: one stored file, held in any number of places.

A file belongs to no workspace: it is visible where one of its holders is (``files/places.py``).
So the fence is not ``OwnedFence`` — a file nobody here holds is refused, one nobody holds at all
passes and is "not found" in the handler's own words. That pass is for reading and deleting
only: attaching the file elsewhere and opening it need a place seen here (``held_here``) — a
live file bound nowhere is an owner left by a failed release, and no workspace may take it before
the reconciliation lets it go.

``IMAGE@`` is the same file as a text shows it: every tool that takes a ``FILE@`` takes it too.

**Deleting** is taking the file out of a place: the binding goes and the holder's storage owner is
released, and the bytes go once nobody holds them. Without a holder only a file held in one place
here is taken out; held in several, the refusal lists them, and the agent repeats naming the one
(``delete(code, holder)``). Each place keeps its holder's write rule: a deleted task is closed,
and a codex note is written only through a mount that lets the agent write.

**Its page** is the file itself, served by ``core_storage_view``.
"""

from __future__ import annotations

from src.modules.core_storage.errors import FileNotFound
from src.modules.core_storage.services.files import file_get
from src.modules.core_storage_view.services.links import public_file_path
from src.modules.tasks.codes import tagged
from src.modules.tasks.constants import FILE_CODE_PREFIX
from src.modules.workbench import session
from src.modules.workbench.codes import bare_code, code_prefix
from src.modules.workbench.contracts import Detachable, Fence, Openable
from src.modules.workbench.files.holders import holder_for
from src.modules.workbench.files.places import Place, bound_anywhere, visible_places
from src.modules.workspace.models.workspace import Workspace

# The form a file takes in a text to be shown as a picture; the code is the file's own.
IMAGE_CODE_PREFIX = "IMAGE"
IMAGE_TYPE = "image"

# The MCP resource a file is read through (``resources.py``) — the model sees it, not a link to it.
FILE_RESOURCE = "workbench://file/{code}"


def file_code(bare: str) -> str:
    return tagged(FILE_CODE_PREFIX, bare) or ""


def bare_file_code(value: str) -> str:
    """The bare code of a ``FILE@`` — or of an ``IMAGE@``, the same file as a text shows it."""
    return bare_code(as_file_code(value), FILE_CODE_PREFIX) or ""


def as_file_code(value: str) -> str:
    """An ``IMAGE@`` as the ``FILE@`` it names, for a tool that dispatches on the type word; any
    other code as it came."""
    if code_prefix(value) != IMAGE_CODE_PREFIX:
        return value
    return f"{FILE_CODE_PREFIX}@{value.partition('@')[2]}"


def resource_uri(bare: str) -> str:
    return FILE_RESOURCE.format(code=bare)


def insert_code(bare: str, file_type: str) -> str:
    """What to put into a text for the file: a picture for an image, a link for anything else."""
    prefix = IMAGE_CODE_PREFIX if file_type == IMAGE_TYPE else FILE_CODE_PREFIX
    return f"{prefix}@{bare}"


def not_attached_here(bare: str, active: Workspace) -> str:
    return (
        f"{file_code(bare)} is not attached to anything in {active.title!r} — a file is visible "
        "where a task of this workspace or a note of a codex mounted here holds it."
    )


def not_found(bare: str) -> str:
    return f"{file_code(bare)} does not exist (or is deleted)."


def _listed(places: list[Place]) -> str:
    return ", ".join(place.listed() for place in places)


async def held_here(bare: str, active: Workspace) -> list[Place]:
    """The file's places seen in ``active`` — at least one, or a refusal: held elsewhere only is
    named as such, held nowhere is "not found", as a read says it."""
    places = await visible_places(bare, active)
    if places:
        return places
    if await bound_anywhere(bare):
        raise ValueError(not_attached_here(bare, active))
    raise ValueError(not_found(bare))


class FileFence(Fence):
    prefix = FILE_CODE_PREFIX

    async def require_visible(self, bare: str, active: Workspace) -> None:
        if await visible_places(bare, active) or not await bound_anywhere(bare):
            return
        raise ValueError(not_attached_here(bare, active))


class FileDeletion(FileFence, Detachable):
    async def delete(self, bare: str) -> bool:
        """Out of its one place here; held in several, refused with their list."""
        active = await session.require_active()
        places = await visible_places(bare, active)
        if not places:
            return False
        if len(places) > 1:
            raise ValueError(
                f"{file_code(bare)} is held in {len(places)} places here: {_listed(places)}. "
                "Nothing was taken out. Say which place to take it out of — "
                f"delete({file_code(bare)!r}, holder=<one of those codes>); a NOTE@ or a STAGE@ "
                "of the task names its task too."
            )
        await places[0].require_detachable(active)
        return await places[0].detach()

    async def detach(self, bare: str, holder: str) -> bool:
        """Out of the one place ``holder`` names; a holder that does not hold it is refused."""
        active = await session.require_active()
        handler, holder_bare = holder_for(holder)
        await handler.require_visible(holder_bare, active)
        target = await handler.locate(holder_bare)
        places = await visible_places(bare, active)
        place = next((place for place in places if target.holds(place)), None)
        if place is None:
            held = f" Here it is held by: {_listed(places)}." if places else ""
            raise ValueError(
                f"{tagged(handler.prefix, holder_bare)} does not hold {file_code(bare)}.{held}"
            )
        await place.require_detachable(active)
        return await place.detach()


class FilePage(FileFence, Openable):
    async def require_visible(self, bare: str, active: Workspace) -> None:
        await held_here(bare, active)

    async def page(self, bare: str) -> str:
        """The file itself, opened in a tab by ``core_storage_view``."""
        try:
            stored = await file_get(bare)
        except FileNotFound:
            raise ValueError(not_found(bare)) from None
        return public_file_path(stored.code)


__all__ = [
    "FILE_RESOURCE",
    "IMAGE_CODE_PREFIX",
    "IMAGE_TYPE",
    "FileDeletion",
    "FileFence",
    "FilePage",
    "as_file_code",
    "bare_file_code",
    "file_code",
    "held_here",
    "insert_code",
    "not_attached_here",
    "not_found",
    "resource_uri",
]
