"""workbench: the MCP bearer-token resolver (``auth.py``) — pure, no DB and no fastmcp.

``Config`` in the module is replaced with a stub so that both branches (empty token = allow-all,
set token = comparison) are deterministic and independent of ``.env`` and the environment.
"""

from __future__ import annotations

import pytest

from src.modules.workbench import auth

pytestmark = pytest.mark.pure


class _Cfg:
    def __init__(self, token: str) -> None:
        self.mcp_token = token


def _use_token(monkeypatch, token: str) -> None:
    monkeypatch.setattr(auth, "Config", lambda: _Cfg(token))


async def test_wrong_scope_rejected(monkeypatch):
    """A token for another scope is a free refusal, before any comparison of the value."""
    _use_token(monkeypatch, "secret")
    assert await auth.resolve_mcp_token("secret", "other") is None


async def test_empty_config_allows_all(monkeypatch):
    _use_token(monkeypatch, "")
    principal = await auth.resolve_mcp_token("", "mcp")
    assert principal is not None
    assert principal.id == 0 and principal.group == "workspace"


async def test_configured_token_matches(monkeypatch):
    _use_token(monkeypatch, "secret")
    principal = await auth.resolve_mcp_token("secret", "mcp")
    assert principal is not None and principal.group == "workspace"


async def test_configured_token_mismatch_rejected(monkeypatch):
    _use_token(monkeypatch, "secret")
    assert await auth.resolve_mcp_token("wrong", "mcp") is None


def test_the_resolver_lives_with_the_servers_it_guards():
    """There must be exactly one provider, and it must be the module that owns the MCP servers.

    ``mount_mcp_servers`` collects the resolver from ALL modules: none — mounting refuses, two —
    likewise. It once sat on ``research``, a module meant to be deleted, and that deletion would
    have brought down MCP entirely. Held by the module that declares the servers, the gate can
    only disappear together with what it guards.
    """
    from src.apps.app.modules import build_modules

    modules = build_modules()
    suppliers = [m.name for m in modules if m.mcp_token_resolver is not None]
    server_owners = [m.name for m in modules if m.mcp_servers]

    assert suppliers == ["workbench"]
    assert server_owners == suppliers
