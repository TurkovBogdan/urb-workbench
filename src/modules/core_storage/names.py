"""The original name of a file as an owner brought it, split into the name and its extension.

The name is a convenience the module keeps for every owner — to show the file and to hand it
out under its name — not metadata it reads: the type of the file still comes from its bytes
first (``mime.detect``), and the extension on disk from the found mime.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import PurePath

from src.core.utils.text import control_character
from src.modules.core_storage.constants import EXTENSION_MAX, ORIGINAL_FILENAME_MAX


@dataclass(frozen=True)
class OriginalName:
    """``filename + extension`` is the name exactly as it came in."""

    filename: str
    extension: str


def split_filename(filename: str) -> OriginalName:
    """The name without its last suffix, and the suffix with its dot, case kept.

    No suffix — the extension is ``''`` and the name stays whole; a dotfile (``.env``) has none.
    A suffix wider than its column stays part of the name, so no part of the name is lost.
    The part that goes into ``original_filename`` is checked against its column before anything
    is written: SQLite stores a longer value and PostgreSQL refuses it, as with ``Owner``. So is a
    control character (``src.core.utils.text``): a name is one line, and U+0000 PostgreSQL
    cannot store at all.
    """
    if not isinstance(filename, str):
        raise ValueError(f"File name must be a string, got {type(filename).__name__}")
    control = control_character(filename)
    if control is not None:
        raise ValueError(
            f"File name holds a control character ({control}) — a name is one line of printable "
            "text; rename the file and send it again"
        )
    suffix = PurePath(filename).suffix
    # ``PurePath`` normalises the name (``x.pdf/``); a suffix not at its very end cannot be cut off.
    if suffix and filename.endswith(suffix) and len(suffix) <= EXTENSION_MAX:
        name = OriginalName(filename=filename[: -len(suffix)], extension=suffix)
    else:
        name = OriginalName(filename=filename, extension="")
    if len(name.filename) > ORIGINAL_FILENAME_MAX:
        raise ValueError(
            f"File name is {len(name.filename)} characters without its extension, "
            f"over the {ORIGINAL_FILENAME_MAX} the column holds"
        )
    return name


__all__ = ["OriginalName", "split_filename"]
