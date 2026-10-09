"""Serving the built SPA (``web/dist``) from the same HTTP server as the API zones.

The core uvicorn is the only web server; the SPA is one of its regular duties (not a separate
server/process). ``mount_spa`` attaches the middleware in the build phase under ``SERVER_ENABLED``
(see ``mount_router_zones``).
"""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from starlette.responses import FileResponse, Response
from starlette.types import ASGIApp, Receive, Scope, Send

from src.core.app_path import project_root
from src.core.loggers import get_logger
from src.core.router.api import API_PREFIX
from src.core.router.internal import INTERNAL_PREFIX
from src.core.router.mcp import MCP_PREFIX
from src.core.router.storage import STORAGE_PREFIX
from src.core.router.webhook import WEBHOOK_PREFIX

_LOG = get_logger()

_API_PREFIXES = (API_PREFIX, INTERNAL_PREFIX, STORAGE_PREFIX, MCP_PREFIX, WEBHOOK_PREFIX)


def _is_api_path(path: str, prefixes: tuple[str, ...]) -> bool:
    """The path belongs to a backend zone (an exact prefix match or a segment under it)."""
    return any(path == prefix or path.startswith(prefix + "/") for prefix in prefixes)


class SpaStaticMiddleware:
    """Serves the bundled frontend (``web/dist``) for any GET/HEAD outside the API prefixes.

    An existing file from ``dist`` is served as is (assets, favicons); every other
    path gets ``index.html`` (a client-side routing deep link). Requests under the
    API prefixes pass through to the backend unchanged — the JSON error contract is not
    affected. The middleware short-circuits serving before routing, so the order in which
    zones are mounted does not matter.
    """

    def __init__(
        self, app: ASGIApp, *, dist: Path, api_prefixes: tuple[str, ...]
    ) -> None:
        self._app = app
        self._dist = dist.resolve()
        self._index = self._dist / "index.html"
        self._api_prefixes = api_prefixes

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        is_browser_get = scope["type"] == "http" and scope["method"] in ("GET", "HEAD")
        if not is_browser_get or _is_api_path(scope["path"], self._api_prefixes):
            await self._app(scope, receive, send)
            return
        await self._spa_response(scope["path"])(scope, receive, send)

    def _spa_response(self, path: str) -> Response:
        relative = path.lstrip("/")
        if relative:
            candidate = (self._dist / relative).resolve()
            if candidate.is_file() and self._dist in candidate.parents:
                return FileResponse(candidate)
        return FileResponse(self._index)


def mount_spa(app: FastAPI) -> None:
    """Mount frontend serving from ``web/dist``; no build → WARNING + no-op."""
    dist = project_root() / "web" / "dist"
    if not (dist / "index.html").is_file():
        _LOG.warning(
            "spa: %s/index.html not found — the frontend is not served; build it "
            "(`pnpm --dir web build`)",
            dist,
        )
        return
    app.add_middleware(SpaStaticMiddleware, dist=dist, api_prefixes=_API_PREFIXES)
    _LOG.info("spa: serving the frontend from %s", dist)
