"""File MCP tools — attach a file to what holds it, and read what a file is.

``attach_file`` is one door for every holder, picked by the code's prefix (``files/holders.py``).
The bytes never pass through the model, in either direction: the agent names a path on the
server's disk, an already stored file, or — when the server cannot reach the file (a remote
server, a path that is not there) — sends the bytes to an upload address with ``curl``. No
base64 anywhere: a file in an argument would cost the agent its size in output tokens.

Taking the bytes is ``core_storage_upload``'s — a path on the server's disk (``server_file``,
``take_server_file``) and the upload request (``open_upload_request``) — and it hands them to the
holder by code (``FileTarget.holder``), with what the agent asked for — the title and the
description — as the holder's payload. Here stay the workspace's fence, the holder's write rule
asked first, the words of every refusal for the agent and the answers' shape.

**The upload request** is written by the upload module once every refusal known now is given; it
keeps the holder, this workspace, the title, the description and the name hint, and the agent gets
only a short address with the request's random token and the command. When the bytes come, the
upload module asks the holder again with the stored workspace — a task may be deleted, a mount may
have lost the agent's right in the minutes between — completes the request once and answers in
this module's words (``files/answers.py``): ``curl`` prints the same shape a direct attach returns.

A path on the server is the agent's own file: it is read, never moved. The server's own files are
not: the kernel's ``/proc``, ``/sys`` and ``/dev``, this installation's ``runtime/`` and its
``.env*`` — links followed first — are refused with the reason. Any other file the server's user
may read is still read, unless the upload module's setting ``server_path_enabled`` is off.
What the server finds there decides the way: a file it reads is attached; a folder or another
non-file is refused; a file it sees and may not open is refused with the reason — it is on this
machine, and the agent either gives the server the right to read it or sends the bytes. A path
the server cannot see at all — relative, absent, behind a folder it may not enter, under the home
of a user it does not know, or any path when the server reads none — may well be the agent's own
on another machine or under another user, so it goes to an upload address.

The upload command is for the agent's shell: a leading ``~`` or ``~user`` stays outside the
quotes, where that shell expands it to the agent's home, not the server's.

``file_get`` is what a file is and the three ways to it: the address it is served at, the MCP
resource that shows it to the model (``resources.py``), and its path where the server runs.

**Names** a workspace sees come only from places it sees (``places.name_here``): ``file_get``
shows the name the file came under at the first such place, and ``attach_file(file=…)`` copies
that name — the storage's own choice, the earliest owner anywhere, would carry a name brought
in another workspace.
"""

from __future__ import annotations

import re
import shlex
from collections.abc import Awaitable
from pathlib import PurePath
from typing import TYPE_CHECKING, TypeVar

from src.modules.core_storage.errors import FileNotFound, StorageError
from src.modules.core_storage.services.files import file_get as file_get_stored
from src.modules.core_storage.services.files import file_path
from src.modules.core_storage.services.ownership import file_owners
from src.modules.core_storage_upload.dto import AttachedFile
from src.modules.core_storage_upload.errors import NotAFile, ServersOwnFile, UnreadableFile
from src.modules.core_storage_upload.services.requests import open_upload_request
from src.modules.core_storage_upload.services.server_path import server_file, take_server_file
from src.modules.core_storage_view.services.links import app_url, public_file_path
from src.modules.tasks.constants import FILE_CODE_PREFIX
from src.modules.workbench.dto import AgentFile, AgentFileAttached, AgentFilePlace, AgentFileUpload
from src.modules.workbench.entities.file import (
    bare_file_code,
    held_here,
    insert_code,
    not_found,
    resource_uri,
)
from src.modules.workbench.files.answers import attached_answer
from src.modules.workbench.files.holders import Binding, FileTarget, holder_for
from src.modules.workbench.files.places import Place, download_here, name_here, visible_places
from src.modules.workbench.scope import require_scope, require_visible
from src.modules.workspace.models.workspace import Workspace

if TYPE_CHECKING:  # fastmcp fork — backend only (via mcp_server(ctx))
    from fastmcp import FastMCP

# Stands in the upload command for a file the server was given no path of.
_LOCAL_FILE = "<local file>"

# ``~`` or ``~user`` as a shell reads it before the first slash.
_HOME_PREFIX = re.compile(r"~[A-Za-z0-9._-]*")

_Taken = TypeVar("_Taken", Binding, AttachedFile)


async def _attached(active: Workspace, binding: Binding | AttachedFile) -> AgentFileAttached:
    return await attached_answer(active.code, active.title, binding)


async def _storing(attach: Awaitable[_Taken]) -> _Taken:
    """The storage's refusals worded like every other: they are not ``ValueError``s of their own.
    A disk failure midway is one too — the storage takes back what it had started."""
    try:
        return await attach
    except StorageError as error:
        raise ValueError(f"{error}.") from error
    except OSError as error:
        raise ValueError(
            f"The server failed on the file ({error.strerror or error}). Nothing was attached."
        ) from error


def _for_shell(path: str) -> str:
    """``path`` quoted for the agent's shell, a leading ``~`` / ``~user`` left outside the quotes:
    a quoted tilde is not expanded, and ``curl`` would look for a folder named ``~``."""
    head, slash, rest = path.partition("/")
    if not _HOME_PREFIX.fullmatch(head):
        return shlex.quote(path)
    return head + slash + (shlex.quote(rest) if rest else "")


async def _name_at(target: FileTarget, file_code: str, places: list[Place]) -> str:
    """The name a stored file takes at ``target``: the one its own row there kept, else the one
    it came under at a place seen here, else none (``''``)."""
    owners = await file_owners(file_code, include_deleted=True)
    own = next((owner for owner in owners if owner.owner == target.owner), None)
    if own is not None:
        return own.original_filename + own.original_extension
    return name_here(places, owners) or ""


def register(mcp: "FastMCP") -> None:

    @mcp.tool()
    async def attach_file(
        code: str,
        title: str = "",
        description: str = "",
        path: str | None = None,
        file: str | None = None,
    ) -> AgentFileAttached:
        """Attach a file to a task, a task note, a stage or a codex note — and get the code to
        put it into a text.

        The holder: TASK@ — the task. NOTE@ or STAGE@ — the same task, with the file marked as
        brought in there; it is not a second place. A file is in a task once, and its code
        serves every text of the task. A file the task already has is refused, whatever its
        name: the same bytes are the same file. To show it in a note or a stage, put its code
        into that text instead — task_get lists the task's files. CODEX@ — a codex note, only
        where codex_index shows the codex editable.

        The file, one of:
        - `path` — a file on the server's disk, read and left where it is. A server on your
          machine reaches your absolute paths; its own files — /proc, /sys, /dev, its runtime
          folder, .env files, database, stored files and copies — it refuses.
        - `file` — a FILE@ already stored here (from task_get, codex_get or file_get): the same
          file, attached to one more holder.
        - neither, or a `path` the server cannot see (another machine, a relative path) — the
          answer carries `upload`: a one-time address, open for minutes, and a ready `command`
          (`curl -T <file> '<url>'`). Nothing is attached until you run it; what it prints is
          this same answer with the file attached. Add `&filename=<name>` to the url to name a
          file sent without a path.

        Attached, the answer has `code` (FILE@) and `insert` — what to put into a text:
        IMAGE@ for a picture (shown as one), FILE@ for anything else (a link). No sorting: a
        new file goes last among the holder's.

        Args:
            code: What holds the file — a TASK@, NOTE@, STAGE@ or CODEX@ (a note) code.
            title: What the file is called at this holder, up to 256 characters; empty shows its
                name.
            description: What is inside the file, up to 256 characters.
            path: The file — an absolute path on the server, or your path to upload from.
            file: Instead of `path` — a FILE@ code of a file stored already.
        """
        if path and file:
            raise ValueError("Pass `path` or `file`, not both — one file is attached per call.")
        handler, bare = holder_for(code)
        active = await require_visible(handler, bare)
        target = await handler.target(bare, active)
        if file:
            stored = bare_file_code(file)
            places = await held_here(stored, active)
            binding = await _storing(
                target.attach_existing(
                    stored,
                    filename=await _name_at(target, stored, places),
                    title=title,
                    description=description,
                )
            )
            return await _attached(active, binding)
        asked = {"title": title, "description": description}
        try:
            source = await server_file(path) if path else None
            if source is not None:
                attached = await _storing(
                    take_server_file(target.holder, source, payload=asked, workspace=active.code)
                )
                return await _attached(active, attached)
        except ServersOwnFile as error:
            raise ValueError(
                f"{path!r} is the server's own file ({error.reason}) — attach_file does not read "
                "system files or the installation's data: its runtime folder, .env files, "
                "database, stored files and copies. Nothing was attached. If you mean a file of "
                "yours, send it: attach_file without `path` gives an upload address."
            ) from error
        except NotAFile as error:
            raise ValueError(
                f"{path!r} on the server is not a file — attach one file per call."
            ) from error
        except UnreadableFile as error:
            raise ValueError(
                f"{path!r} is on the server, but the server cannot read it ({error.reason}). "
                "Nothing was attached. Let the server's user read it, or send the bytes: "
                "attach_file without `path` gives an upload address."
            ) from error
        address = await open_upload_request(
            target.holder,
            workspace=active.code,
            payload=asked,
            filename_hint=PurePath(path).name if path else "",
        )
        local = _for_shell(path) if path else shlex.quote(_LOCAL_FILE)
        return AgentFileAttached(
            workspace=active.code,
            workspace_title=active.title,
            upload=AgentFileUpload(
                url=address.url,
                path=address.path,
                expires_at=address.expires_at,
                command=f"curl -T {local} {shlex.quote(address.url)}",
            ),
        )

    @mcp.tool()
    async def file_get(file_code: str) -> AgentFile:
        """Read what a file is, where it is held here, and how to get at it.

        `url` opens it; `download_url` saves it under its `name` here. `resource` shows it to
        you through MCP — a picture as a picture, text as text; other types only download.
        `path` is where its bytes lie on the server — when the server runs on your machine,
        reading it directly is the shortest way to look at the file; never write there. `places` — the holders here: a task (once, whatever
        note or stage the file came in through) or a codex note, with what the file is called
        and holds at each; name one as `holder` in delete to take the file out of it.

        Args:
            file_code: The file — a FILE@ code (an IMAGE@ in a text names the same file).
        """
        bare = bare_file_code(file_code)
        active = await require_scope(FILE_CODE_PREFIX, bare)
        places = await visible_places(bare, active)
        try:
            stored = await file_get_stored(bare) if places else None
        except FileNotFound:
            stored = None
        if stored is None:
            raise ValueError(not_found(bare))
        owners = await file_owners(stored.code, include_deleted=True)
        return AgentFile(
            workspace=active.code,
            workspace_title=active.title,
            code=stored.code,
            insert=insert_code(stored.code, stored.type),
            name=name_here(places, owners) or f"{stored.code}{stored.extension}",
            mime=stored.mime,
            type=stored.type,
            size=stored.size,
            url=app_url(public_file_path(stored.code)),
            download_url=app_url(download_here(stored.code, places, owners)),
            resource=resource_uri(stored.code),
            path=str(file_path(stored)),
            places=[
                AgentFilePlace(
                    holder=place.holder, title=place.title, description=place.description
                )
                for place in places
            ],
        )


__all__ = ["register"]
