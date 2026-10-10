"""``WORKSPACE@`` on the agent surface: its fence and its page."""

from __future__ import annotations

from src.modules.workbench.contracts import Openable, OwnedFence
from src.modules.workspace.constants import WORKSPACE_CODE_PREFIX


class WorkspaceFence(OwnedFence):
    prefix = WORKSPACE_CODE_PREFIX

    async def owner(self, bare: str) -> str | None:
        """A workspace owns itself: its code is compared with the active one directly."""
        return bare


class WorkspacePage(WorkspaceFence, Openable):
    async def page(self, bare: str) -> str:
        """A workspace has no card page of its own: it lives as a row in the list."""
        return "/workspaces"


__all__ = ["WorkspaceFence", "WorkspacePage"]
