"""Routes of a task transfer: the export, and the three steps of an import with its cancel.

Upload → analysis → apply are separate requests on purpose: while the person reads the plan the
base does not change, and the analysis and the apply are different functions with different rights
to write. Cancelling removes the uploaded file at once rather than leaving it for the day's sweep.

The import lives under ``/transfer``, not under ``/tasks/…``: an upload id next to the task routes
would be one more segment for ``/tasks/{code}`` to argue with.
"""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Query, Request, Response
from fastapi.responses import FileResponse
from pydantic import BaseModel, ConfigDict, Field
from starlette.background import BackgroundTask

from src.core.api import ApiError
from src.modules.core_transfer.errors import DECISION_INVALID, PLAN_CHANGED, UPLOAD_NOT_FOUND, TransferError
from src.modules.core_transfer.uploads import drop_file
from src.modules.tasks.codes import bare_code
from src.modules.tasks.constants import GROUP_CODE_PREFIX, TASK_CODE_PREFIX
from src.modules.tasks.crud import group as group_crud
from src.modules.tasks.crud import task as task_crud
from src.modules.tasks.errors import GROUP_DELETED, GROUP_NOT_FOUND, TASK_DELETED, TASK_NOT_FOUND
from src.modules.tasks.transfer.collect import export_task
from src.modules.tasks.transfer.constants import TASK_ARCHIVE
from src.modules.tasks.transfer.plan import plan_body
from src.modules.tasks.transfer.runner import UPLOADS, analyze_archive, import_archive
from src.modules.workspace.constants import WORKSPACE_CODE_PREFIX
from src.modules.workspace.crud.workspace import workspace_get
from src.modules.workspace.errors import WORKSPACE_DELETED, WORKSPACE_NOT_FOUND

router = APIRouter()


class _Body(BaseModel):
    model_config = ConfigDict(extra="forbid")


class AnalyzeBody(_Body):
    workspace: str


class ApplyBody(_Body):
    workspace: str
    group_code: str | None = None
    decisions: dict[str, str] = Field(default_factory=dict)
    plan_token: str


class UploadedArchive(BaseModel):
    upload_id: str
    file_name: str
    size: int


def _bare(value: str, prefix: str) -> str:
    try:
        return bare_code(value, prefix) or ""
    except ValueError as error:
        raise ApiError.bad_request(str(error)) from error


def _refusal(error: TransferError) -> ApiError:
    if error.code == UPLOAD_NOT_FOUND:
        return ApiError.not_found(str(error), code=error.code, params=error.params)
    if error.code == PLAN_CHANGED:
        return ApiError.conflict(str(error), code=error.code, params=error.params)
    if error.code == DECISION_INVALID:
        return ApiError.validation(str(error), code=error.code, params=error.params)
    return ApiError.bad_request(str(error), code=error.code, params=error.params)


async def _live_workspace(value: str) -> str:
    code = _bare(value, WORKSPACE_CODE_PREFIX)
    row = await workspace_get(code, include_deleted=True)
    if row is None:
        raise ApiError.not_found("Workspace not found", code=WORKSPACE_NOT_FOUND)
    if row.deleted_at is not None:
        raise ApiError.conflict("The workspace is deleted", code=WORKSPACE_DELETED)
    return code


async def _group_of(value: str | None, workspace_code: str) -> str | None:
    if not value:
        return None
    code = _bare(value, GROUP_CODE_PREFIX)
    row = await group_crud.group_get(code, include_deleted=True)
    if row is None or row.workspace_code != workspace_code:
        raise ApiError.not_found("Group not found in this workspace", code=GROUP_NOT_FOUND)
    if row.deleted_at is not None:
        raise ApiError.conflict("The group is deleted", code=GROUP_DELETED)
    return code


@router.get("/tasks/{code}/export")
async def export_route(code: str) -> FileResponse:
    """The task as a ``.utsk`` archive, named by its title."""
    bare = _bare(code, TASK_CODE_PREFIX)
    row = await task_crud.task_get(bare, include_deleted=True)
    if row is None:
        raise ApiError.not_found("Task not found", code=TASK_NOT_FOUND)
    if row.deleted_at is not None:
        raise ApiError.conflict("The task is deleted — restore it to export", code=TASK_DELETED)
    path = UPLOADS.export_path()
    try:
        archive = await export_task(bare, path)
    except BaseException:
        drop_file(path)
        raise
    return FileResponse(
        path=archive.path,
        media_type=TASK_ARCHIVE.media_type,
        filename=archive.file_name,
        background=BackgroundTask(drop_file, archive.path),
    )


@router.post("/transfer/upload")
async def upload_route(
    request: Request, filename: Annotated[str, Query(max_length=255)] = ""
) -> UploadedArchive:
    """Take the file as the request body — the first of the import's steps."""
    try:
        stored = await UPLOADS.take(request.stream(), filename)
    except TransferError as error:
        raise _refusal(error) from error
    return UploadedArchive(upload_id=stored.upload_id, file_name=stored.file_name, size=stored.size)


@router.post("/transfer/{upload_id}/analyze")
async def analyze_route(upload_id: str, body: AnalyzeBody) -> dict[str, Any]:
    """What the import would do to the workspace; writes nothing."""
    workspace = await _live_workspace(body.workspace)
    try:
        stored = UPLOADS.get(upload_id)
        plan = await analyze_archive(stored.path, workspace_code=workspace)
    except TransferError as error:
        raise _refusal(error) from error
    return plan_body(plan, file_name=stored.file_name, size=stored.size)


@router.post("/transfer/{upload_id}/apply")
async def apply_route(upload_id: str, body: ApplyBody) -> dict[str, Any]:
    """Import into the workspace and the group, with a choice for every conflict."""
    workspace = await _live_workspace(body.workspace)
    group = await _group_of(body.group_code, workspace)
    try:
        stored = UPLOADS.get(upload_id)
        plan, report = await import_archive(
            stored.path,
            workspace_code=workspace,
            group_code=group,
            decisions=body.decisions,
            plan_token=body.plan_token,
        )
    except TransferError as error:
        raise _refusal(error) from error
    UPLOADS.drop(upload_id)
    return report.body(list(plan.content.manifest.dangling_refs))


@router.delete("/transfer/{upload_id}", status_code=204)
async def cancel_route(upload_id: str) -> Response:
    UPLOADS.drop(upload_id)
    return Response(status_code=204)


__all__ = ["router"]
