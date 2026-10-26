"""What the module hands out: plain frozen values."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class ServedFile:
    """A stored file ready to go out: where its bytes lie and how to present them.

    ``stat_result`` is the proof the bytes are on disk, taken before the answer is built:
    ``FileResponse`` that finds them missing raises, and the miss would come out a 500 instead of
    the 404 every other miss gets.
    ``filename`` is the name to hand it out under; ``code + extension`` is its name on disk.
    """

    code: str
    path: Path
    stat_result: os.stat_result
    mime: str
    sha256: str
    extension: str
    filename: str


__all__ = ["ServedFile"]
