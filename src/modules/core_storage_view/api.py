"""The module's routes in the ``/storage`` zone — one file, three addresses.

- ``GET|HEAD /storage/{store}/{code}`` — the bytes of a served file, to open in the tab;
- ``…/{code}/download`` — the same bytes, saved under the neutral ``<CODE><ext>``;
- ``…/{code}/download/{name}`` — saved under ``name`` (``services/serving.py``).

Headers come from ``headers.py``. Any miss is one 404, the same body for every code.

The zone's guard is ``allow_all``: the files of ``public`` are open by meaning.

The refusal carries no ``code``: it is read by a browser tab, an ``<img>`` and ``curl``, never by
the interface's dictionary, and the status alone tells it.
"""

from __future__ import annotations

from fastapi import APIRouter, Request, Response
from fastapi.responses import FileResponse

from src.core.api import ApiError
from src.modules.core_storage.errors import FileNotFound
from src.modules.core_storage_view.constants import DOWNLOAD_SEGMENT
from src.modules.core_storage_view.headers import etag_matches, file_headers
from src.modules.core_storage_view.services.serving import served_file

router = APIRouter()


@router.api_route("/{store}/{code}", methods=["GET", "HEAD"])
async def open_file(store: str, code: str, request: Request) -> Response:
    return await _serve(request, store, code, download=False)


@router.api_route(f"/{{store}}/{{code}}/{DOWNLOAD_SEGMENT}", methods=["GET", "HEAD"])
async def download_file(store: str, code: str, request: Request) -> Response:
    return await _serve(request, store, code, download=True)


@router.api_route(f"/{{store}}/{{code}}/{DOWNLOAD_SEGMENT}/{{name}}", methods=["GET", "HEAD"])
async def download_named_file(store: str, code: str, name: str, request: Request) -> Response:
    return await _serve(request, store, code, download=True, name=name)


async def _serve(
    request: Request, store: str, code: str, *, download: bool, name: str | None = None
) -> Response:
    try:
        file = await served_file(store, code, name=name)
    except FileNotFound:
        raise ApiError.not_found("File not found") from None
    headers = file_headers(file, download=download)
    if etag_matches(request.headers.get("if-none-match"), headers["ETag"]):
        return Response(status_code=304, headers=headers)
    return FileResponse(file.path, media_type=file.mime, headers=headers, stat_result=file.stat_result)


__all__ = ["router"]
