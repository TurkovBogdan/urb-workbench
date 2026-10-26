"""The archive's file name, made of the entity's title.

A title is human text: slashes, colons, quotes, emoji, a newline, a trailing dot. The file lands
on someone else's file system, so the name is cleaned down to what Windows and POSIX both take,
and what is left of the entity is exactly its title.
"""

from __future__ import annotations

import re

# Path separators and the characters Windows forbids in a file name, plus control characters.
_UNSAFE = re.compile(r'[\x00-\x1f\x7f<>:"/\\|?*]+')
_SPACES = re.compile(r"\s+")

# Counted in code points, not bytes: in UTF-8 Cyrillic weighs twice, and a byte limit would cut
# Russian titles twice as short as English ones.
MAX_STEM_LENGTH = 80


def archive_file_name(title: str, *, fallback: str, extension: str) -> str:
    """``<clean title><extension>``; nothing left of the title — ``<fallback><extension>``."""
    # Whitespace first: a newline in a title is a space between its words, not a forbidden dash.
    stem = _UNSAFE.sub("-", _SPACES.sub(" ", title)).strip()
    # Windows does not open a file whose name ends with a dot or a space.
    stem = stem[:MAX_STEM_LENGTH].rstrip(" .")
    # A title of forbidden characters only turns into a fence of dashes with no tie to the entity.
    if not stem.strip("-. "):
        stem = ""
    return f"{stem or fallback}{extension}"


__all__ = ["MAX_STEM_LENGTH", "archive_file_name"]
