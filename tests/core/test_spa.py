"""spa: the frontend-serving middleware — the API-prefix boundary and file resolution."""

from __future__ import annotations

import pytest

from src.core.router.spa import SpaStaticMiddleware, _is_api_path

_API = ("/api", "/internal", "/storage", "/mcp", "/webhook")


async def _noop_app(scope, receive, send):  # pragma: no cover — downstream stub
    raise AssertionError("downstream must not be called for SPA paths")


@pytest.mark.pure
@pytest.mark.parametrize(
    "path,is_api",
    [
        ("/api", True),
        ("/api/things", True),
        ("/internal/health", True),
        ("/storage/x", True),
        ("/apidocs", False),  # the prefix must match on a segment, not a substring
        ("/", False),
        ("/login", False),
        ("/assets/index-abc.js", False),
    ],
)
def test_is_api_path_matches_on_segment_boundary(path: str, is_api: bool):
    assert _is_api_path(path, _API) is is_api


@pytest.mark.pure
def test_spa_response_serves_file_else_index(tmp_path):
    (tmp_path / "index.html").write_text("<div id=\"app\"></div>")
    (tmp_path / "assets").mkdir()
    asset = tmp_path / "assets" / "a.js"
    asset.write_text("export {}")
    mw = SpaStaticMiddleware(_noop_app, dist=tmp_path, api_prefixes=_API)

    index = (tmp_path / "index.html").resolve()
    assert mw._spa_response("/assets/a.js").path == asset.resolve()
    # a client-side routing deep link → index.html
    assert mw._spa_response("/conversations/42").path == index
    # escaping dist (traversal) → index.html, not a file outside it
    assert mw._spa_response("/../secret").path == index
