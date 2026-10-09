"""Refusal codes of the workspace HTTP layer.

A human reads them in the interface: the interface looks the code ``workspace.<entity>.<reason>``
up in its dictionary (``workspace.error.<entity>.<reason>``), and the response text is the
English fallback for when there is no translation. Modules a level above (``tasks``) use the same
codes when they look up a workspace themselves.
"""

from __future__ import annotations

WORKSPACE_NOT_FOUND = "workspace.workspace.not_found"
WORKSPACE_DELETED = "workspace.workspace.deleted"
WORKSPACE_NOT_DELETED = "workspace.workspace.not_deleted"

__all__ = ["WORKSPACE_DELETED", "WORKSPACE_NOT_DELETED", "WORKSPACE_NOT_FOUND"]
