"""The agent's answer for a file attached — the same whichever way the bytes came.

``attach_file`` answers with it at once for a path on the server or a stored file; the PUT that
completes an upload request is answered by ``core_storage_upload``, which knows no agent, so this
module hands it ``upload_answer`` (registered in ``WorkbenchModule.configure``): ``curl`` prints
the same shape ``attach_file`` would have returned.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from src.modules.codex.models import CodexFile
from src.modules.core_storage.services.files import file_get
from src.modules.core_storage_upload.dto import AttachedFile, UploadRequest
from src.modules.tasks.models.file import TasksFile
from src.modules.workbench.dto import AgentFileAttached
from src.modules.workbench.entities.file import insert_code
from src.modules.workspace.crud.workspace import workspace_get


async def attached_answer(
    workspace_code: str, workspace_title: str, binding: TasksFile | CodexFile | AttachedFile
) -> AgentFileAttached:
    stored = await file_get(binding.file_code)
    return AgentFileAttached(
        workspace=workspace_code,
        workspace_title=workspace_title,
        code=stored.code,
        insert=insert_code(stored.code, stored.type),
        title=binding.title,
        description=binding.description,
    )


async def upload_answer(request: UploadRequest, attached: AttachedFile) -> Mapping[str, Any]:
    """The answer ``curl`` prints after the upload ``attach_file`` asked for."""
    workspace = await workspace_get(request.workspace, include_deleted=True)
    title = workspace.title if workspace is not None else ""
    return (await attached_answer(request.workspace, title, attached)).model_dump(mode="json")


__all__ = ["attached_answer", "upload_answer"]
