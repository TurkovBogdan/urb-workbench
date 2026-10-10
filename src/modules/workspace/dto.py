"""DTOs of the ``workspace`` module — the web viewer's contracts.

The agent's view of a workspace is not here: it belongs to the agent surface, the ``workbench``
module (``workbench/dto.py``), and shares only ``WorkspaceCode`` with this file. The surfaces
share no contracts even where the field sets coincide — ``WorkspaceListRow`` and
``AgentWorkspaceRow`` describe the same table row and have diverged on purpose. The human needs
styling and counter label keys, the agent needs numbers; merge them into one class and a field
added for a column starts costing the agent context in every session.

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


__all__ = [
    "WorkspaceCode",
    "WorkspaceCounterRow",
    "WorkspaceListRow",
    "WorkspaceRow",
]
