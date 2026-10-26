"""Which page a browser request came from — the app's own, or any other site open in the browser.

The server listens on localhost and its zones have no auth, so a page of another site can still
reach it: CORS keeps that page from reading the answer, not from sending the request. A ``POST``
whose body is ``text/plain`` or a form's is a simple request — the browser sends it with no
``OPTIONS`` ahead — and a route that writes on such a body (a file upload) would act on it. A
WebSocket is not covered by CORS at all.

A browser names the page in ``Origin``. Allowed are the backend's own origin (``Origin`` and
``Host`` name the same address) and the dev origins of ``Config.cors_origins`` (the Vite server).
A request with no ``Origin`` is not a browser's — ``curl``, the agent, a script — and passes:
the threat is a page in the person's browser, not a program the person runs.

Not a defence against DNS rebinding: a rebound name sends a matching ``Origin`` and ``Host``.
"""

from __future__ import annotations

from urllib.parse import urlsplit

from starlette.requests import HTTPConnection

from src.core.api.errors import ApiError

ORIGIN_REFUSED = "origin_refused"


def origin_allowed(origin: str | None, host: str | None, dev_origins: list[str]) -> bool:
    if origin is None:
        return True
    return urlsplit(origin).netloc == host or origin in dev_origins


def connection_dev_origins(connection: HTTPConnection) -> list[str]:
    """The dev origins of the app's config; none on an app built without one (a bare test app)."""
    config = getattr(connection.app.state, "config", None)
    return list(config.cors_origins) if config is not None else []


async def same_origin_only(connection: HTTPConnection) -> None:
    """A route dependency: a request a page of another site sent is refused before its body is
    read. Put it on a route that writes on a body a simple cross-site request can carry."""
    headers = connection.headers
    if not origin_allowed(headers.get("origin"), headers.get("host"), connection_dev_origins(connection)):
        raise ApiError.forbidden(
            "The request came from a page of another site", code=ORIGIN_REFUSED
        )


__all__ = ["ORIGIN_REFUSED", "connection_dev_origins", "origin_allowed", "same_origin_only"]
