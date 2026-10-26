"""The order a files section sends when the holder keeps some files out of sight.

The section (`web/src/components/files/AttachedFiles.vue`) may show only some of the holder's files
— a task hides its notes' files until asked — while the holder puts the codes it is sent on top and
the rest below. So the order goes out whole (`components/files/order.ts::placeShown`): an unseen file
keeps its place among the shown ones.

The scenarios live in `web_file_order.mjs` and run under Node against the real file; each is its
own process. Without Node the tests are skipped.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

pytestmark = pytest.mark.pure

HARNESS = Path(__file__).with_name("web_file_order.mjs")


def _run(*args: str) -> subprocess.CompletedProcess[str]:
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node not found — nothing to execute the order with")
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
