"""MCP resources of the ``workbench`` server — a file, shown to the model rather than linked.

``workbench://file/{code}`` gives a picture as a picture and text as text, so the model looks at
the file itself; anything else is refused with the address to download it from. The workspace
fence holds as for every tool: a file is read only where something here holds it.

A ceiling keeps one read from flooding the context: a resource travels whole inside one MCP
message, base64 for a picture. A file over it is downloaded instead.

``fastmcp`` is imported inside the functions: this module is pulled in with the server's builder,
and the worker must stay without the fork.
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

from src.modules.core_storage.errors import FileNotFound
from src.modules.core_storage.services.files import file_get, file_path
from src.modules.core_storage.services.ownership import file_owners
from src.modules.core_storage_view.services.links import app_url
from src.modules.tasks.constants import FILE_CODE_PREFIX
from src.modules.workbench.entities.file import (
    FILE_RESOURCE,
    IMAGE_TYPE,
    bare_file_code,
    file_code,
)
from src.modules.workbench.files.places import download_here, visible_places
from src.modules.workbench.scope import require_scope

if TYPE_CHECKING:  # fastmcp fork — backend only (via mcp_server(ctx))
    from fastmcp import FastMCP

# The stored categories a resource shows; the rest is downloaded.
TEXT_TYPE = "text"
RESOURCE_MAX_BYTES = 10 * 1024 * 1024


async def file_content(code: str) -> tuple[bytes | str, str]:
    """The file as the model reads it — bytes of a picture or text — and its mime; a refusal
    names where to get it instead."""
    bare = bare_file_code(code)
    active = await require_scope(FILE_CODE_PREFIX, bare)
    places = await visible_places(bare, active)
    try:
        stored = await file_get(bare) if places else None
    except FileNotFound:
        stored = None
    if stored is None:
        raise ValueError(f"{file_code(bare)} does not exist (or is deleted).")
    owners = await file_owners(stored.code, include_deleted=True)
    url = app_url(download_here(stored.code, places, owners))
    if stored.type not in (IMAGE_TYPE, TEXT_TYPE):
        raise ValueError(
            f"{file_code(stored.code)} is {stored.type} ({stored.mime}) — a resource shows "
            f"pictures and text only. Download it from {url}."
        )
    if stored.size > RESOURCE_MAX_BYTES:
        raise ValueError(
            f"{file_code(stored.code)} is {stored.size} bytes, over the {RESOURCE_MAX_BYTES} a "
            f"resource carries. Download it from {url}."
        )
    try:
        data = await asyncio.to_thread(file_path(stored).read_bytes)
    except FileNotFoundError:
        raise ValueError(f"{file_code(stored.code)} has lost its bytes on the server.") from None
    content = data if stored.type == IMAGE_TYPE else data.decode("utf-8", errors="replace")
    return content, stored.mime


def register(mcp: "FastMCP") -> None:
    from fastmcp.exceptions import ResourceError
    from fastmcp.resources import ResourceContent, ResourceResult

    # No return annotation: the fork resolves annotations against this module's globals, and the
    # result types are imported here, inside the builder, to keep the worker without the fork.
    @mcp.resource(
        FILE_RESOURCE,
        name="file",
        description=(
            "A file attached here, shown to you: a picture as a picture, text as text. `code` is "
            "the file's code, bare or as FILE@; file_get gives the whole URI. A client that saves "
            "a picture to disk instead of showing it names the path — open the file there. Other "
            "types, and files over 10 MB, are downloaded from the url file_get gives."
        ),
    )
    async def file(code: str):
        try:
            content, mime = await file_content(code)
        except ValueError as error:
            raise ResourceError(str(error)) from error
        return ResourceResult([ResourceContent(content, mime_type=mime)])


__all__ = ["RESOURCE_MAX_BYTES", "file_content", "register"]
