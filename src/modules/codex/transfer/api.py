"""Routes of a codex transfer: the export, and the three steps of an import with its cancel.

A codex belongs to no workspace, so the analysis needs none; the apply takes one only to mount the
imported codex there (``null`` — mount nowhere).
"""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Query, Request, Response
from fastapi.responses import FileResponse
from pydantic import BaseModel, ConfigDict, Field
from starlette.background import BackgroundTask

from src.core.api import ApiError
from src.modules.codex.codes import bare_code
from src.modules.codex.constants import CODEX_CODE_PREFIX
from src.modules.codex.crud import codex as codex_crud
from src.modules.codex.errors import CODEX_NOT_FOUND
from src.modules.codex.transfer.collect import export_codex
from src.modules.codex.transfer.constants import CODEX_ARCHIVE
from src.modules.codex.transfer.plan import plan_body
from src.modules.codex.transfer.runner import UPLOADS, analyze_archive, import_archive
from src.modules.core_transfer.errors import (
    DECISION_INVALID,
    DEPTH_EXCEEDED,
    PLAN_CHANGED,
    UPLOAD_NOT_FOUND,
    TransferError,
)
from src.modules.core_transfer.uploads import drop_file
from src.modules.workspace.codes import bare_code as workspace_bare
from src.modules.workspace.constants import WORKSPACE_CODE_PREFIX
from src.modules.workspace.crud.workspace import workspace_get
from src.modules.workspace.errors import WORKSPACE_DELETED, WORKSPACE_NOT_FOUND

router = APIRouter()


class _Body(BaseModel):
    model_config = ConfigDict(extra="forbid")


class AnalyzeBody(_Body):
    pass


class ApplyBody(_Body):
    workspace: str | None = None
    decisions: dict[str, str] = Field(default_factory=dict)
    plan_token: str


class UploadedArchive(BaseModel):
    upload_id: str
    file_name: str
    size: int


def _refusal(error: TransferError) -> ApiError:
    if error.code == UPLOAD_NOT_FOUND:
        return ApiError.not_found(str(error), code=error.code, params=error.params)
    if error.code in (PLAN_CHANGED, DEPTH_EXCEEDED):
        return ApiError.conflict(str(error), code=error.code, params=error.params)
    if error.code == DECISION_INVALID:
        return ApiError.validation(str(error), code=error.code, params=error.params)
    return ApiError.bad_request(str(error), code=error.code, params=error.params)


def _bare(value: str, prefix: str) -> str:
    try:
        return bare_code(value, prefix) or ""
    except ValueError as error:
        raise ApiError.bad_request(str(error)) from error


async def _live_workspace(value: str | None) -> str | None:
    if not value:
        return None
    try:
        code = workspace_bare(value, WORKSPACE_CODE_PREFIX) or ""
    except ValueError as error:
        raise ApiError.bad_request(str(error)) from error
    row = await workspace_get(code, include_deleted=True)
    if row is None:
        raise ApiError.not_found("Workspace not found", code=WORKSPACE_NOT_FOUND)
    if row.deleted_at is not None:
        raise ApiError.conflict("The workspace is deleted", code=WORKSPACE_DELETED)
    return code


@router.get("/codexes/{code}/export")
async def export_route(code: str) -> FileResponse:
    """The whole codex as a ``.ucdx`` archive, named by its title — from the bin too."""
    bare = _bare(code, CODEX_CODE_PREFIX)
    if await codex_crud.codex_get(bare, include_deleted=True) is None:
        raise ApiError.not_found("Codex not found", code=CODEX_NOT_FOUND)
    path = UPLOADS.export_path()
    try:
        archive = await export_codex(bare, path)
    except BaseException:
        drop_file(path)
        raise
    return FileResponse(
        path=archive.path,
        media_type=CODEX_ARCHIVE.media_type,
        filename=archive.file_name,
        background=BackgroundTask(drop_file, archive.path),
    )


@router.post("/transfer/upload")
async def upload_route(
    request: Request, filename: Annotated[str, Query(max_length=255)] = ""
) -> UploadedArchive:
    try:
        stored = await UPLOADS.take(request.stream(), filename)
    except TransferError as error:
        raise _refusal(error) from error
    return UploadedArchive(upload_id=stored.upload_id, file_name=stored.file_name, size=stored.size)


@router.post("/transfer/{upload_id}/analyze")
async def analyze_route(upload_id: str, body: AnalyzeBody | None = None) -> dict[str, Any]:
    try:
        stored = UPLOADS.get(upload_id)
        plan = await analyze_archive(stored.path)
    except TransferError as error:
        raise _refusal(error) from error
    return plan_body(plan, file_name=stored.file_name, size=stored.size)


@router.post("/transfer/{upload_id}/apply")
async def apply_route(upload_id: str, body: ApplyBody) -> dict[str, Any]:
    workspace = await _live_workspace(body.workspace)
    try:
        stored = UPLOADS.get(upload_id)
        plan, report = await import_archive(
            stored.path, workspace_code=workspace, decisions=body.decisions, plan_token=body.plan_token,
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
