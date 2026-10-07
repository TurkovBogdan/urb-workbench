"""The change feed store keeps its connection: reconnect, deadlines, echo, resync.

`web/src/stores/changes.ts` owns everything the browser no longer does for it since the feed moved
from `EventSource` to a WebSocket: the reconnect and its pause, the deadline on a handshake nobody
answers, the watchdog on a link that went silent. None of it shows on a healthy screen — a broken
reconnect is a tab that quietly stops updating — so it is checked here.

The scenarios live in `web_changes_feed.mjs` and run under Node (`--experimental-strip-types`)
against the real store, with a fake socket and a fake clock; each scenario is its own process, so
no state leaks between them. Without Node the tests are skipped.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

pytestmark = pytest.mark.pure

HARNESS = Path(__file__).with_name("web_changes_feed.mjs")


def _run(*args: str, protocol: str = "http:") -> subprocess.CompletedProcess[str]:
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node not found — nothing to execute the store with")
    return subprocess.run(
        [node, "--experimental-strip-types", "--no-warnings", str(HARNESS), *args],
        capture_output=True,
        text=True,
        env={"PATH": "", "FEED_PROTOCOL": protocol},
    )


def _scenarios() -> list[str]:
    if shutil.which("node") is None:
        return ["node-missing"]
    listed = _run("--list")
    assert listed.returncode == 0, listed.stderr
    return json.loads(listed.stdout)


@pytest.mark.parametrize("scenario", _scenarios())
def test_scenario(scenario: str):
    result = _run(scenario)
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "ok"


def test_secure_page_opens_a_secure_socket():
    result = _run("opens_one_socket_on_the_feed_path", protocol="https:")
    assert result.returncode == 0, result.stderr
