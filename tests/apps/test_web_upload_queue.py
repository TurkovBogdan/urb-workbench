"""The files card's upload queue: a file goes to the holder it was dropped on.

The card (`web/src/components/files/AttachedFiles.vue`) outlives its holder — the task page keeps
its components when the person follows a link to another task — so the queue
(`components/files/uploadQueue.ts`) takes the holder and its upload with each file, at the moment
the file is queued, and shows a row on its own holder only.

The scenarios live in `web_upload_queue.mjs` and run under Node against the real file; each is its
own process. Without Node the tests are skipped.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

pytestmark = pytest.mark.pure

HARNESS = Path(__file__).with_name("web_upload_queue.mjs")


def _run(*args: str) -> subprocess.CompletedProcess[str]:
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node not found — nothing to execute the upload queue with")
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
