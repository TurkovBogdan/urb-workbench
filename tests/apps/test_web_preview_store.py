"""The preview store asks only for what it lacks and keeps what it holds fresh.

`web/src/stores/preview.ts` is invisible when it works and silently wrong when it does not: a pill
that shows yesterday's title, or a body that fires a request per render. Its rules — one request
per tick, misses kept, a change re-asking the codes it names, wide events re-asking everything,
a map per workspace asked, an answer of the previous workspace dropped, a page's workspace kept
while the page holds it — are checked here.

The scenarios live in `web_preview_store.mjs` and run under Node (`--experimental-strip-types`)
against the real store, with the lookup client and the change feed faked; each scenario is its own
process. Without Node the tests are skipped.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

pytestmark = pytest.mark.pure

HARNESS = Path(__file__).with_name("web_preview_store.mjs")


def _run(*args: str) -> subprocess.CompletedProcess[str]:
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node not found — nothing to execute the store with")
    return subprocess.run(
        [node, "--experimental-strip-types", "--no-warnings", str(HARNESS), *args],
        capture_output=True,
        text=True,
        env={"PATH": ""},
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
