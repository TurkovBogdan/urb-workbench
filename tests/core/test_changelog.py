"""Changelog reader — `CHANGELOG.md` and `docs/changelog/<language>.md` for the About page, and the
route serving it."""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.core import changelog as changelog_module
from src.core.app_path import project_root
from src.core.changelog import (
    SOURCE_FILE,
    SOURCE_LANGUAGE,
    TRANSLATIONS_FOLDER,
    read_changelog,
    releases,
    translation_path,
)
from src.core.update.api import router

pytestmark = pytest.mark.pure

SOURCE = (
    "# Changelog\n\nEnglish · [Русский](docs/changelog/ru.md)\n\n## [1.2.3] — 2026-10-26\n\n- One.\n"
)
RUSSIAN = "# Журнал\n\n[English](../../CHANGELOG.md) · Русский\n\n## [1.2.3]\n\n- Один.\n"


def _checkout(root: Path, *, source: str | None = SOURCE, **translations: str) -> Path:
    if source is not None:
        (root / SOURCE_FILE).write_text(source, encoding="utf-8")
    for language, text in translations.items():
        path = translation_path(root, language)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    return root


def test_releases_drop_the_title_and_the_language_links():
    assert releases(SOURCE) == "## [1.2.3] — 2026-10-26\n\n- One."


def test_a_file_without_a_release_heading_is_shown_whole():
    assert releases("\nJust a note.\n") == "Just a note."


def test_reads_the_translation_asked_for(tmp_path: Path):
    found = read_changelog(_checkout(tmp_path, ru=RUSSIAN), "ru")
    assert found is not None
    assert found.language == "ru"
    assert found.text == "## [1.2.3]\n\n- Один."


def test_english_is_the_source_in_the_root(tmp_path: Path):
    found = read_changelog(_checkout(tmp_path, ru=RUSSIAN), SOURCE_LANGUAGE)
    assert found is not None
    assert found.language == SOURCE_LANGUAGE
    assert found.text.startswith("## [1.2.3] — 2026-10-26")


def test_a_language_without_a_translation_reads_the_source(tmp_path: Path):
    found = read_changelog(_checkout(tmp_path), "de")
    assert found is not None
    assert found.language == SOURCE_LANGUAGE


@pytest.mark.parametrize("language", ["../../CHANGELOG", "RU", "ru.md", "", "rus"])
def test_anything_but_a_language_code_reads_the_source(tmp_path: Path, language: str):
    found = read_changelog(_checkout(tmp_path, ru=RUSSIAN), language)
    assert found is not None
    assert found.language == SOURCE_LANGUAGE


def test_a_translation_without_the_source_is_still_read(tmp_path: Path):
    found = read_changelog(_checkout(tmp_path, source=None, ru=RUSSIAN), "ru")
    assert found is not None
    assert found.language == "ru"


def test_no_file_at_all_is_none(tmp_path: Path):
    assert read_changelog(tmp_path, "ru") is None


def _client(monkeypatch: pytest.MonkeyPatch, root: Path) -> TestClient:
    monkeypatch.setattr(changelog_module, "project_root", lambda: root)
    app = FastAPI()
    # The router's own `GET ""` needs a prefix, as the zone mounts it under one.
    app.include_router(router, prefix="/update")
    return TestClient(app)


def test_route_answers_with_the_language_it_read(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    client = _client(monkeypatch, _checkout(tmp_path))
    answer = client.get("/update/changelog", params={"language": "ru"}).json()
    assert answer == {"language": "en", "text": "## [1.2.3] — 2026-10-26\n\n- One."}


def test_route_without_a_changelog_answers_empty(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    answer = _client(monkeypatch, tmp_path).get("/update/changelog").json()
    assert answer == {"language": None, "text": None}


UNRELEASED = "unreleased"


def _release_headings(path: Path) -> list[str]:
    """The releases in order; the section with no number yet is named in each file's own language
    (`[Unreleased]`, `[Не выпущено]`), so it counts as one and the same."""
    labels = re.findall(r"^## \[([^\]]+)\]", path.read_text(encoding="utf-8"), re.MULTILINE)
    return [label if label[:1].isdigit() else UNRELEASED for label in labels]


def test_an_unreleased_section_matches_across_languages(tmp_path: Path):
    _checkout(
        tmp_path,
        source="## [Unreleased]\n\n## [1.2.3] — 2026-10-26\n",
        ru="## [Не выпущено]\n\n## [1.2.3] — 2026-10-26\n",
    )
    assert _release_headings(tmp_path / SOURCE_FILE) == [UNRELEASED, "1.2.3"]
    assert _release_headings(translation_path(tmp_path, "ru")) == [UNRELEASED, "1.2.3"]


def test_every_translation_has_the_releases_of_the_source():
    """A translation follows `CHANGELOG.md` release by release: a missing one is news withheld."""
    source = _release_headings(project_root() / SOURCE_FILE)
    assert source
    translations = sorted((project_root() / TRANSLATIONS_FOLDER).glob("*.md"))
    assert translations
    for translation in translations:
        assert _release_headings(translation) == source, translation.name
