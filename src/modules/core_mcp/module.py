"""Module provider of the core_mcp module.

An infra module for MCP server introspection: the application surface over the foundation in
``src/core/mcp/`` (that one amends the ``Module`` contract and mounts the sub-apps — it cannot
be a module). This side only reads: the ``/core-mcp/servers`` API returns the list of servers
brought up, their tools and the connection config for the UI. No tables/migrations/settings of
its own; it reads the live instances from ``app.state.mcp_servers``.
"""

from __future__ import annotations

from typing import ClassVar

from fastapi import FastAPI

from src.core.config import Config
from src.core.module import Module
from src.modules.core_mcp.api import router as mcp_router


class CoreMcpModule(Module):
    name: ClassVar[str] = "core_mcp"
    description: ClassVar[str] = "Introspection of the running MCP servers: their tools and connection config."
    migrations_dir = None
    config_cls = None
    settings_schema = None
    internal_router = mcp_router
    internal_router_prefix = "/core-mcp"

    def configure(self, app: FastAPI, config: Config) -> None:
        pass


__all__ = ["CoreMcpModule"]
