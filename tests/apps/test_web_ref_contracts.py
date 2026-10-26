"""The entity-code contract of the markdown zones: which codes become pills and where they lead.

`web/src/components/markdown/shared/contracts.ts` is what the renderer and the editor must not
disagree about, and it mirrors the backend lookup's set of types: a type missing here is a code
the backend can describe and no body can show. Its rules — every type read as itself, a group not
mistaken for a task, a wrong-length hash left as text, the address the code alone can tell — are
checked here, plus one pinned flaw (no left word boundary).

The scenarios live in `web_ref_contracts.mjs` and run under Node against the real file; each is
its own process. Without Node the tests are skipped.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

pytestmark = pytest.mark.pure

HARNESS = Path(__file__).with_name("web_ref_contracts.mjs")


def _run(*args: str) -> subprocess.CompletedProcess[str]:
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node not found — nothing to execute the contract with")
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


def test_the_vocabulary_matches_the_backend_lookup(config):
    """The pill vocabulary and the registered lookup prefixes are one set."""
    from fastapi import FastAPI

    from src.apps.app.modules import build_modules
    from src.modules.core_lookup.registry import registered_types

    app = FastAPI()
    for module in build_modules():
        module.configure(app, config)
    backend = {kind.prefix for kind in registered_types()}

    assert len(backend) == 9
    source = (Path(__file__).parents[2] / "web/src/components/markdown/shared/contracts.ts").read_text()
    vocabulary = source.split("export const REF_TYPES = [", 1)[1].split("]", 1)[0]
    assert {word.strip(" '") for word in vocabulary.split(",")} == backend
