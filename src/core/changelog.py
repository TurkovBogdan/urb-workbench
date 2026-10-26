"""Changelog of this checkout — `CHANGELOG.md` and its translations, for the About page.

Read from the checkout like the release number (`src/core/version.py`): the page shows what is
installed, so after an update the backend that comes back shows the new text without a rebuilt
frontend.

The source is the root `CHANGELOG.md`, in English, where a reader of the repository looks first.
Its translations lie in `docs/changelog/`, one file per language named by its code as the
interface dictionaries are (`web/src/locales/<code>.json`) — twenty languages stay out of the
root. A language without a translation reads the source.

The page shows the releases, not the file: the title and the line of language links above the
first release heading are the file's own furniture — the card has a title, and a link to another
file leads nowhere inside the app.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from src.core.app_path import project_root

SOURCE_FILE = "CHANGELOG.md"
SOURCE_LANGUAGE = "en"
TRANSLATIONS_FOLDER = Path("docs") / "changelog"

# A language code is all the request may put into a file name.
_LANGUAGE = re.compile(r"^[a-z]{2}$")
_RELEASE_HEADING = re.compile(r"^## ", re.MULTILINE)


@dataclass(frozen=True)
class Changelog:
    # The language the text is in — the one asked for, or the source's when it has no file.
    language: str
    text: str


def releases(text: str) -> str:
    """The text from the first release heading on; a file without one is shown whole."""
    first = _RELEASE_HEADING.search(text)
    return (text[first.start():] if first else text).strip()


def translation_path(root: Path, language: str) -> Path:
    return root / TRANSLATIONS_FOLDER / f"{language}.md"


def read_changelog(root: Path, language: str) -> Changelog | None:
    """The changelog in `language`, else the source; `None` — neither file is read."""
    candidates: list[tuple[str, Path]] = []
    if _LANGUAGE.match(language) and language != SOURCE_LANGUAGE:
        candidates.append((language, translation_path(root, language)))
    candidates.append((SOURCE_LANGUAGE, root / SOURCE_FILE))
    for candidate, path in candidates:
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            continue
        return Changelog(language=candidate, text=releases(text))
    return None


def installed_changelog(language: str) -> Changelog | None:
    """The changelog of the running checkout. Read on every call, as the release number is."""
    return read_changelog(project_root(), language)


__all__ = [
    "SOURCE_FILE",
    "SOURCE_LANGUAGE",
    "TRANSLATIONS_FOLDER",
    "Changelog",
    "installed_changelog",
    "read_changelog",
    "releases",
    "translation_path",
]
