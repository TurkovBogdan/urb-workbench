"""Names of the headers the stdio shim introduces itself to the backend with.

They live in a separate leaf module rather than in ``src/core/mcp/`` on purpose: that package
imports ``fastmcp`` (+13 MB) from its ``__init__``, while these two strings are needed on both
ends of the wire — by the shim (``apps/app/mcp_stdio.py``, where the fork is pulled in lazily)
and by the tool on the backend. A shared constant here is cheaper than two string literals that
drift apart at the first rename.

**Why headers at all.** The MCP servers are mounted as ``stateless_http`` (see
``core/router/mcp.py``): the server keeps no sessions, every call is a standalone HTTP request.
Yet there is one backend for everyone — shared by every agent connection and by the browser
with the UI. So "who is calling" can only arrive from outside, and this is where it arrives.

- ``MCP_SESSION_HEADER`` — the conversation's identifier, sent unchanged until the shim dies. The
  shim takes it from the client's environment when the client names its conversation there, so
  a shim the client restarts mid-conversation comes back under the same key; otherwise it makes
  up a random one per process. This key IS the session boundary: the backend keys the active
  workspace on it.
- ``MCP_WORKSPACE_HEADER`` — the workspace from the launch config. It is the connection's
  DEFAULT, not a binding: a session that has not been assigned a workspace works in this one;
  once assigned, the agent's choice overrides the config and does not touch the file.

The headers come from the client and are, strictly speaking, forgeable. That is not a threat
here: the server listens on localhost behind a bearer token, and only someone who can already
call the tools directly could forge another session.
"""

from __future__ import annotations

MCP_SESSION_HEADER = "x-workbench-session"
MCP_WORKSPACE_HEADER = "x-workbench-workspace"

__all__ = ["MCP_SESSION_HEADER", "MCP_WORKSPACE_HEADER"]
