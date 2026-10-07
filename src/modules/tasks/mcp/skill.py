"""Reference MCP tools — skills the agent fetches before work instead of carrying them in context.

Two tools: the catalogue (name and trigger condition, no texts) and reading — whole or one
section. The texts are files in ``skills/`` and are served as is; all logic is in
``services/skills.py``.

Nothing can guarantee that a skill gets loaded: an instruction in a description competes with
the model's confidence, and the client is free to outweigh it. So pointers sit where the
reference is needed, and responsibility does not end with the skill itself — **a pointer is an
optimization; the guarantee comes from the tool's refusal**. Whatever can be checked is enforced
by refusal: evidence when closing a stage, the entry type, a task's terminal status.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from pydantic import BaseModel

from src.modules.tasks.services.skills import list_skills, read_skill

if TYPE_CHECKING:  # fastmcp fork — backend only (via mcp_server(ctx))
    from fastmcp import FastMCP


# A catalogue row: everything but the text. Cheap to call — that is the point of the first level.
class AgentSkillRow(BaseModel):
    model_config = {"from_attributes": True}

    name: str
    description: str
    sections: list[str] = []


# A whole skill or one section. ``sections`` comes along here too: having read the body, the agent
# sees which branch to follow next and does not have to go back to the catalogue.
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
