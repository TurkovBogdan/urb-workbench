"""Files pasted or dropped into an editor field: what is taken, what goes into the text, and where.

A field with a holder (`MarkdownEditor`'s `attach`) uploads the files a paste or a drop brings and
puts their codes where they were put (`web/src/components/markdown/editor/behavior/fileAttach.ts`).
Three things would break silently and are checked here: a paste of text taken for a paste of
files (or the reverse), codes glued to each other or to a word, and a placeholder that lands
somewhere else after the text around it changed — or leaves half a code behind.

The scenarios live in `web_file_attach.mjs` and run under Node against the real files; each is its
own process. Without Node the tests are skipped.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

pytestmark = pytest.mark.pure

HARNESS = Path(__file__).with_name("web_file_attach.mjs")


def _run(*args: str) -> subprocess.CompletedProcess[str]:
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node not found — nothing to execute the editor extension with")
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
