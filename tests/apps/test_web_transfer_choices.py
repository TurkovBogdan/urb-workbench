"""The choices of an import's conflicts in the window — the same rules the server checks.

The import window (`TaskImportDialog`, `CodexImportDialog`) offers «update» and «replace» per
conflict; `components/transfer/types.ts` keeps them consistent: nothing chosen by default, a
dependent «update» falling back to «replace» once what it requires is replaced, the choices of a
changed plan carried over where they still fit.

The scenarios live in `web_transfer_choices.mjs` and run under Node against the real file; each is
its own process. Without Node the tests are skipped.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

pytestmark = pytest.mark.pure

HARNESS = Path(__file__).with_name("web_transfer_choices.mjs")


def _run(*args: str) -> subprocess.CompletedProcess[str]:
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node not found — nothing to execute the choices with")
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
