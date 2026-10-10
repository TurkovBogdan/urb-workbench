"""Skill catalogue — reference the agent fetches on demand instead of carrying it in context.

A skill is a ``skills/<name>/`` folder with a ``SKILL.md`` file and optional sections
``sections/<section>.md``. Three levels of disclosure: the name with its trigger condition costs
a dozen tokens, the body arrives for a task, a section for a branch of the task.

The reference lives as files inside the module and is versioned in the same commit as the code
it describes. Reference that has drifted is worse than none: the agent treats it as
authoritative and confidently does the wrong thing by it.

The skill name comes from the agent, so no path is assembled from it: we open only the folders
we found on disk ourselves.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

SKILLS_DIR = Path(__file__).resolve().parent.parent / "skills"

_SKILL_FILE = "SKILL.md"
_SECTIONS_DIR = "sections"
_FRONTMATTER_FENCE = "---"


@dataclass(frozen=True)
class SkillSummary:
    """A catalogue row — everything but the text."""

    name: str
    description: str
    sections: list[str]


@dataclass(frozen=True)
class SkillPage:
    """A skill as read: the whole body or one section (``section`` is empty for the whole)."""

    name: str
    section: str
    description: str
    sections: list[str]
    text: str


def _skill_dirs() -> dict[str, Path]:
    if not SKILLS_DIR.is_dir():
        return {}
    return {
        candidate.name: candidate
        for candidate in sorted(SKILLS_DIR.iterdir())
        if (candidate / _SKILL_FILE).is_file()
    }


def _section_files(skill_dir: Path) -> dict[str, Path]:
    sections_dir = skill_dir / _SECTIONS_DIR
    if not sections_dir.is_dir():
        return {}
    return {section.stem: section for section in sorted(sections_dir.glob("*.md"))}


def _split_frontmatter(raw: str) -> tuple[str, str]:
    """Split the frontmatter ``description`` from the body; no frontmatter — empty description."""
    if not raw.startswith(_FRONTMATTER_FENCE):
        return "", raw
    _, _, after_opening = raw.partition("\n")
    frontmatter, closing, body = after_opening.partition(f"{_FRONTMATTER_FENCE}\n")
    if not closing:
        return "", raw
    description = ""
    for line in frontmatter.splitlines():
        key, separator, value = line.partition(":")
        if separator and key.strip() == "description":
            description = value.strip()
    return description, body.lstrip("\n")


def _read_skill_file(skill_dir: Path) -> tuple[str, str]:
    return _split_frontmatter((skill_dir / _SKILL_FILE).read_text(encoding="utf-8"))


def list_skills() -> list[SkillSummary]:
    """The catalogue: name, trigger condition, section names — without the texts."""
    catalogue = []
    for name, skill_dir in _skill_dirs().items():
        description, _ = _read_skill_file(skill_dir)
        catalogue.append(
            SkillSummary(
                name=name, description=description, sections=list(_section_files(skill_dir))
            )
        )
    return catalogue


def read_skill(skill_name: str, section: str | None = None) -> SkillPage:
    """A whole skill or one of its sections; an unknown name is refused with the available list."""
    skill_dirs = _skill_dirs()
    skill_dir = skill_dirs.get(skill_name)
    if skill_dir is None:
        available = ", ".join(skill_dirs) or "none"
        raise ValueError(f"Unknown skill {skill_name!r}. Available: {available}.")

    description, text = _read_skill_file(skill_dir)
    sections = _section_files(skill_dir)
    if section:
        section_file = sections.get(section)
        if section_file is None:
            known = ", ".join(sections) or "none — call it without a section"
            raise ValueError(
                f"Skill {skill_name!r} has no section {section!r}. Sections: {known}."
            )
        text = section_file.read_text(encoding="utf-8")

    return SkillPage(
        name=skill_name,
        section=section or "",
        description=description,
        sections=list(sections),
        text=text,
    )


__all__ = ["SKILLS_DIR", "SkillPage", "SkillSummary", "list_skills", "read_skill"]
