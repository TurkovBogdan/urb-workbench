"""McpServerTokenVerifier — the agnostic bearer verifier of MCP servers (pure)."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from src.core.mcp import McpServerTokenVerifier

pytestmark = pytest.mark.pure


async def test_verify_token_maps_principal_to_access_token():
    """The resolver's principal → AccessToken(client_id=str(id), scopes=[group])."""

    async def resolve(token: str, scope: str):
        return SimpleNamespace(id=7, group="manager") if token == "good" else None

    at = await McpServerTokenVerifier(resolve).verify_token("good")
    assert at is not None
    assert at.token == "good"
    assert at.client_id == "7"
    assert at.scopes == ["manager"]


async def test_verify_token_none_when_resolver_rejects():
    """resolve → None (unknown/expired/foreign scope) ⇒ verify_token → None."""

    async def resolve(token: str, scope: str):
        return None

    assert await McpServerTokenVerifier(resolve).verify_token("whatever") is None


async def test_verify_token_requests_mcp_scope():
    """The verifier asks the resolver strictly for scope 'mcp' (token typing)."""
    seen: dict[str, str] = {}

    async def resolve(token: str, scope: str):
        seen["scope"] = scope
        return None

    await McpServerTokenVerifier(resolve).verify_token("x")
    assert seen["scope"] == "mcp"
