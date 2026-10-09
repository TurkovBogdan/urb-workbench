"""DTOs of the ``workspace`` module — the contracts of both surfaces: the web viewer and the agent.

**The ``Agent`` prefix = the agent surface.** A class with this prefix is returned by the MCP
tools (``mcp/``) and by nobody else; everything else is a web viewer contract. The boundary is
solid: the surfaces share no contracts even where the field sets coincide — ``WorkspaceListRow``
and ``AgentWorkspaceRow`` describe the same table row and have diverged on purpose. The human
needs styling and counter label keys, the agent needs numbers; merge them into one class and a
field added for a column starts costing the agent context in every session.

The agent class has no docstring on purpose: pydantic puts it into the tool's JSON schema as the
description, and the agent pays for it on every connection. So explanations of agent contracts
live in comments ABOVE the class.

A code in the output carries the presentation prefix (``WORKSPACE@…``) — ``prefixed`` from
``workspace.codes`` handles that: the serializer adds the type word only in JSON, the internal
``model_dump()`` stays bare. On input a code is accepted in both forms — ``bare_code`` strips the
prefix at the endpoint boundary, not here: a DTO describes the response, parsing the path is the
route's job.

Dates are returned as the core's ``DatetimeUTCStr`` (SQL format without ``T``) — exactly what
the frontend parser ``web/src/shared/utils/date.ts`` (Luxon ``fromSQL``) expects.

The workspace's contents are not in the response and cannot be: the module does not know what
lives in it. Instead come the **counters** declared by the modules above (``stats.py``) — a
"key + how many" pair plus a label key by which the interface finds the text.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from src.core.utils.date import DatetimeUTCStr
from src.modules.workspace.codes import prefixed
from src.modules.workspace.constants import SORT_DEFAULT, WORKSPACE_CODE_PREFIX

# The presentation code type: the bare hash inside, ``WORKSPACE@<hash>`` outside.
WorkspaceCode = prefixed(WORKSPACE_CODE_PREFIX)


class WorkspaceRow(BaseModel):
    """The whole workspace: it has no body, so the list scan and the detail are one field set.

    ``deleted_at`` goes out on purpose: the list can show deleted ones (``include_deleted``), and
    the client must tell a live card from a deleted one by the data, not by which request it
    came from.
    """

    model_config = ConfigDict(from_attributes=True)

    code: WorkspaceCode
    title: str
    description: str = ""
    color: str = ""
    icon: str = ""
    # Position in the list: higher ``sort`` — higher up, as for a task group.
    sort: int = SORT_DEFAULT
    created_at: DatetimeUTCStr
    updated_at: DatetimeUTCStr
    deleted_at: DatetimeUTCStr | None = None


class WorkspaceCounterRow(BaseModel):
    """One contents counter: whose it is, how to label it and how many were counted.

    The label is a message key, not text: Russian text in a module that knows nothing about
    language would be a second place to edit on every rename.
    """

    key: str
    label_key: str
    count: int


class WorkspaceListRow(WorkspaceRow):
    """A list row: the card plus counters of what the modules above keep in it.

    Counters count only live items: a deleted row does not exist for the rest of the code, and
    showing it as "3 zones inside" would promise the human something they will not find inside.
    The delete dialog reads these same numbers — which is why the counters live in the list row
    rather than being fetched by a separate request every time the dialog opens.

    The counter set is not a fixed contract: it depends on which modules are up. An empty list is
    a legitimate answer (nobody declared anything), and the interface draws the card without
    numbers.
    """

    counters: list[WorkspaceCounterRow] = []


# The workspace the call ran in — goes into EVERY response of a bound tool. Not a service field
# and not debugging: the agent has no other way to notice it is working in the wrong context — a
# list of someone else's tasks looks like a list of tasks, and an empty one like "no work". A
# named workspace turns this mistake from invisible into obvious from the first response, and it
# costs two fields.
class AgentScope(BaseModel):
    workspace: WorkspaceCode
    workspace_title: str


# A workspace through the agent's eyes: what it is called, what is inside and whether the agent
# works in it. Counters come as a flat dict (``{"groups": 2, "tasks": 12}``), not as a list of
# rows with label keys as in the interface: a label key is needed by whoever renders human text,
# while the agent needs a number next to a name. The key set depends on the application's
# composition — it is the same registry (``stats.py``), and it is not a fixed contract.
class AgentWorkspaceRow(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    code: WorkspaceCode
    title: str
    description: str = ""
    counters: dict[str, int] = {}
    active: bool = False


# The binding response: the same workspace plus what the agent does not know about its choice —
# how long it lasts and what makes it permanent.
class AgentWorkspaceBound(AgentWorkspaceRow):
    note: str


__all__ = [
    "AgentScope",
    "AgentWorkspaceBound",
    "AgentWorkspaceRow",
    "WorkspaceCode",
    "WorkspaceCounterRow",
    "WorkspaceListRow",
    "WorkspaceRow",
]
