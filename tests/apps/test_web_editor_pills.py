"""Entity codes in an editor field: a code stays its own word, and marks around it hold.

A code in an editor field is a pill (`entityRef`, `web/src/components/markdown/editor/blocks/
entityRef.ts`); the field stores markdown, so whether the code survives is decided by the bridge
(`editor/bridge/`). Two things broke silently: text right after a pill was printed glued to the code
(`IMAGE@ABCDEF0123текст` — before a hex letter the code is not a code any more), and a bold or
italic run around a pill came back split in two (`**a** CODE **b**`). Both are checked here — the
bridge in both directions, a load and save with nothing edited, a save after an edit elsewhere, and
a paste of text next to a pill (`editor/behavior/markdownPaste.ts`).

The scenarios live in `web_editor_pills.mjs` and run under Node against the real files; each is its
own process. Without Node the tests are skipped.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

pytestmark = pytest.mark.pure

HARNESS = Path(__file__).with_name("web_editor_pills.mjs")


def _run(*args: str) -> subprocess.CompletedProcess[str]:
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node not found — nothing to execute the editor bridge with")
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
