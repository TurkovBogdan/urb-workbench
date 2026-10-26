"""Files dragged in from the computer: folders, the size ceiling, the window's guard, the slash command.

A file dropped beside a drop zone must not take the browser away from the app, a zone that will not
take files must say so with the "no" cursor, a folder must be refused while the files beside it go,
and a field with a holder must offer a way to attach a file without dragging. The pure parts live in
``web/src/shared/utils/fileDrop.ts`` and ``fileDrag.ts`` and in the slash menu
(``components/markdown/editor/controls/slashMenu.ts``); what would break silently is checked here:
a folder taken for a file, a drag that never ends on screen, a drag begun on the page (a block, a
piece of text) mistaken for files, the file command offered where a file has nowhere to go.

The scenarios live in ``web_file_drop.mjs`` and run under Node against the real files; each is its
own process. Without Node the tests are skipped.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

pytestmark = pytest.mark.pure

HARNESS = Path(__file__).with_name("web_file_drop.mjs")


def _run(*args: str) -> subprocess.CompletedProcess[str]:
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node not found — nothing to execute the drop helpers with")
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
