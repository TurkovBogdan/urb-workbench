"""MCP-тулы справки — навыки, которые агент забирает перед работой, а не носит в контексте.

Два тула: каталог (имя и условие вызова, без текстов) и чтение — целиком или одним разделом.
Тексты лежат файлами в ``skills/`` и отдаются как есть; вся логика в ``services/skills.py``.

Загрузку навыка ничем нельзя гарантировать: указание в описании конкурирует с уверенностью
модели, и клиент вправе его перевесить. Поэтому указатели стоят там, где справка нужна, а
ответственность на самом навыке не заканчивается — **указатель это оптимизация, гарантию даёт
отказ инструмента**. Всё, что можно проверить, проверяется отказом: доказательство при закрытии
этапа, тип записи, чужая постановка.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from pydantic import BaseModel

from src.modules.tasks.services.skills import list_skills, read_skill

if TYPE_CHECKING:  # fork fastmcp — только backend (через mcp_server(ctx))
    from fastmcp import FastMCP


# Строка каталога: всё, кроме текста. Дёшево звать — в этом и смысл первого уровня.
class AgentSkillRow(BaseModel):
    model_config = {"from_attributes": True}

    name: str
    description: str
    sections: list[str] = []


# Навык целиком или один раздел. ``sections`` едет и здесь: прочитав тело, агент видит, за какой
# веткой идти дальше, и не обязан возвращаться в каталог.
class AgentSkill(BaseModel):
    model_config = {"from_attributes": True}

    name: str
    section: str = ""
    description: str
    sections: list[str] = []
    text: str


def register(mcp: "FastMCP") -> None:

    @mcp.tool()
    async def skills_list() -> list[AgentSkillRow]:
        """List the skills this server can teach you — name, when to use it, its sections.

        A skill is reference material kept here: how this app expects a brief, a plan or a
        journal to be written, and what its interface actually renders. It is the difference
        between output that works the way it looks and output that quietly does not.

        Cheap to call — the catalogue carries no skill text, only names and the condition each
        one is for. Read one with skill_get(skill_name).
        """
        return [AgentSkillRow.model_validate(skill) for skill in list_skills()]

    @mcp.tool()
    async def skill_get(skill_name: str, section: str | None = None) -> AgentSkill:
        """Return a skill — the whole guide, or one section of it.

        Read it BEFORE the work it covers, not after the result comes back wrong. Your own
        sense of how a task should be written is not the question: what matters is what THIS
        app does with it, and that is what the skill describes.

        Args:
            skill_name: The skill to read — a name from skills_list.
            section: One name from that skill's `sections`; omit for the whole guide.
        """
        return AgentSkill.model_validate(read_skill(skill_name, section))


__all__ = ["AgentSkill", "AgentSkillRow", "register"]
