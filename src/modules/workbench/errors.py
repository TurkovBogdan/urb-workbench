"""Named refusals of the MCP surface's rules.

The same technique as in ``tasks/errors.py``: the rule code is separate from the text because
there are two readers. The agent reads the English phrase and fixes the call by it; the interface
(and future tests) look at the code, which survives any rewording of the phrase.

Both refusals here are about the **scope**, not the data, and both exist to make working in the
wrong workspace loud. Quietly taking a list of someone else's tasks is worse than refusing: a
scope error does not look like an error, it looks like an empty list or someone else's work.
"""

from __future__ import annotations

NO_ACTIVE_WORKSPACE = "no_active_workspace"
"""The session is not bound to a workspace, and the tool is meaningless without one."""

WORKSPACE_MISMATCH = "workspace_mismatch"
"""An entity code points into a workspace other than this session's active one."""


class WorkspaceScopeError(ValueError):
    """A scope refusal with a machine name.

    A ``ValueError`` subclass on purpose: ``fastmcp`` turns it into an execution error
    (``isError``), which by the spec is returned to the model — so that it corrects itself and
    retries the call. That is the only channel through which a tool can teach anything.
    """

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


def no_active_workspace() -> WorkspaceScopeError:
    """The "no workspace chosen" refusal — naming both tools that fix it.

    The text spells out the whole path rather than stating what is missing: an agent told "no
    active workspace" without the second half of the phrase will start looking for a tool
    argument that is not there.
    """
    return WorkspaceScopeError(
        NO_ACTIVE_WORKSPACE,
        "This session is not bound to a workspace yet, and this tool works inside one. "
        "Call workspaces_list() to see what exists, then workspace_use(workspace_code) to "
        "pick one — after that no tool needs a workspace argument.",
    )


def workspace_mismatch(
    *, code: str, owner_code: str, owner_title: str, active_code: str, active_title: str
) -> WorkspaceScopeError:
    """The "code from another workspace" refusal — with the titles of both, not just codes.

    The titles in the text are not decoration: codes are random and indistinguishable by eye,
    while "Personal versus Work" the agent understands at once and fixes the right way — by
    switching the workspace or the code, not by repeating the same call.
    """
    return WorkspaceScopeError(
        WORKSPACE_MISMATCH,
        f"{code} belongs to workspace {owner_code} ({owner_title!r}), but this session works "
        f"in {active_code} ({active_title!r}). A workspace is a hard boundary here: either "
        f"pass a code from {active_title!r}, or switch with workspace_use({owner_code}).",
    )


__all__ = [
    "NO_ACTIVE_WORKSPACE",
    "WORKSPACE_MISMATCH",
    "WorkspaceScopeError",
    "no_active_workspace",
    "workspace_mismatch",
]
