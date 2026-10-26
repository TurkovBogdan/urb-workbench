"""`IMAGE@` pictures in the editor: the stored text is untouched, and galleries match the viewer's.

A picture in an editor field is the same reference node as a pill, drawn as the picture
(`web/src/components/markdown/editor/blocks/entityRef/EntityImageView.vue`). Two things would
break silently: a field loaded and saved with nothing edited coming back with other bytes, and the
editor paging a gallery the viewer draws differently. Both are checked here — the bridge round trip
for every task and codex field set, and the editor's gallery rule (`blocks/entityRef/imageRuns.ts`)
against the viewer's (`renderer/render.ts`) on the same texts. The layout both zones share is checked too: the column
count by the size of a gallery (`shared/pictures.ts`), the same column class on every picture in
both zones, and where the editor breaks the line around a run and which blanks it hides. So is a
picture moved by a drag or Alt+←/→ (`blocks/entityRef/pictureMove.ts`): the text it leaves and the
text it lands in keep their codes apart by one blank, and a drop that changes nothing is no move.

The scenarios live in `web_editor_images.mjs` and run under Node against the real files; each is
its own process. Without Node the tests are skipped.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

pytestmark = pytest.mark.pure

HARNESS = Path(__file__).with_name("web_editor_images.mjs")


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
