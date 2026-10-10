"""What a handler of a shared method must answer — by itself, from nothing but the code.

The shared tools (``content_*``, ``delete``, ``interface_open``) and the workspace fence take a
code of any type and hand it to the handler registered for its prefix. A handler is the whole
knowledge of one entity type on the agent surface, and two questions are always its own:

- **where the row is.** It gets the bare code and finds the row itself — one table, or several
  under one prefix; the tool never names a model.
- **whether the row is visible in the active workspace** (``require_visible``). An entity owned by
  one workspace answers by comparing the owner (``OwnedFence``); one shared across several
  workspaces answers by whatever links it to them. Missing rows pass: the handler's own action
  says "not found" in its own words, more precisely than a fence could.

A registry is a plain ``prefix → handler`` dict built by ``by_prefix``: the order of registration
is the order the tools list the accepted types in their refusals, so it is a contract with the
agent, not an accident.
"""

from __future__ import annotations

from typing import ClassVar, TypeVar

from src.modules.workbench.codes import tagged
from src.modules.workbench.errors import workspace_mismatch
from src.modules.workspace.codes import tagged as workspace_tagged
from src.modules.workspace.constants import WORKSPACE_CODE_PREFIX
from src.modules.workspace.crud import workspace as workspace_crud
from src.modules.workspace.models.workspace import Workspace


class Fence:
    """One entity type's answer to "may this code be acted on from the active workspace"."""

    prefix: ClassVar[str]

    async def require_visible(self, bare: str, active: Workspace) -> None:
        """Refuse, naming the way out, when the entity is not visible in ``active``."""
        raise NotImplementedError


class OwnedFence(Fence):
    """An entity that lives in exactly one workspace: a foreign owner is refused by name.

    The refusal names both workspaces with their titles — codes are random and indistinguishable
    by eye, while "Personal versus Work" tells the agent at once to switch rather than retry.
    """

    async def owner(self, bare: str) -> str | None:
        """The bare code of the owning workspace; ``None`` — there is no such entity."""
        raise NotImplementedError

    async def require_visible(self, bare: str, active: Workspace) -> None:
        owner = await self.owner(bare)
        if owner is None or owner == active.code:
            return
        holder = await workspace_crud.workspace_get(owner, include_deleted=True)
        raise workspace_mismatch(
            code=str(tagged(self.prefix, bare)),
            owner_code=str(workspace_tagged(WORKSPACE_CODE_PREFIX, owner)),
            owner_title=holder.title if holder else "unknown",
            active_code=str(workspace_tagged(WORKSPACE_CODE_PREFIX, active.code)),
            active_title=active.title,
        )


class Deletable(Fence):
    """An entity ``delete`` removes — and whatever its type says goes with it."""

    async def delete(self, bare: str) -> bool:
        """Delete by the bare code; ``False`` — nothing was there to delete."""
        raise NotImplementedError


class Openable(Fence):
    """An entity ``interface_open`` can put on the person's screen."""

    async def page(self, bare: str) -> str:
        """The app path that shows the entity — its own page, its owner's, or its list."""
        raise NotImplementedError


Handler = TypeVar("Handler", bound=Fence)


def by_prefix(*handlers: Handler) -> dict[str, Handler]:
    """A registry from handlers, in the given order; one prefix twice is a wiring error."""
    registry: dict[str, Handler] = {}
    for handler in handlers:
        if handler.prefix in registry:
            raise RuntimeError(f"Two handlers registered for {handler.prefix}@.")
        registry[handler.prefix] = handler
    return registry


__all__ = ["Deletable", "Fence", "Openable", "OwnedFence", "by_prefix"]
