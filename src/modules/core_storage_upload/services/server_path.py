"""A file named by its path on the server's disk — read, never moved, and never the server's own.

The path is the client's word for a file it has. What the server finds there decides the way:

- a file it reads — taken (``take_server_file``);
- a folder or another non-file — ``NotAFile``;
- a file it sees and may not open — ``UnreadableFile``: it is on this machine, and the client
  either gives the server the right to read it or sends the bytes;
- a path it cannot see at all — relative, absent, behind a folder it may not enter, under the
  home of a user it does not know — ``None``: the file may well be the client's own on another
  machine or under another user, and the bytes have to be sent.

The server's own files are not taken: the kernel's ``/proc``, ``/sys`` and ``/dev``, this
installation's ``runtime/``, its ``.env*``, its SQLite file, stores and copies wherever the
settings put them — links followed first, and again on the file actually opened — are
``ServersOwnFile`` with the reason. Any other file the server's user may read is still read; the module's setting
``server_path_enabled`` turns the reading off for a server whose disk the client must not reach
(then every path is ``None``, and the client sends the bytes).

The refusals are not worded for a reader here: the caller knows who asked and what else they can
do, and says it.
"""

from __future__ import annotations

import asyncio
import os
import stat
from collections.abc import AsyncIterator
from enum import Enum
from pathlib import Path
from typing import BinaryIO

from src.core.app_path import project_root, resolve_runtime_root
from src.core.backup import BACKUP_FOLDER_NAME
from src.core.config import get_config
from src.modules.core_storage.services.registration import file_spool
from src.modules.core_storage_upload.constants import CHUNK_SIZE
from src.modules.core_storage_upload.dto import AttachedFile, Payload
from src.modules.core_storage_upload.errors import NotAFile, ServersOwnFile, UnreadableFile
from src.modules.core_storage_upload.services.holders import upload_holder
from src.modules.core_storage_upload.services.intake import kept_name, refuse_oversize
from src.modules.core_storage_upload.settings import server_path_enabled

# The kernel's views of the processes and devices: never a file a client means to hand over.
_SYSTEM_ROOTS = (Path("/proc"), Path("/sys"), Path("/dev"))


class _Reach(Enum):
    READABLE = "readable"
    NOT_A_FILE = "not a file"
    SEALED = "sealed"
    UNSEEN = "unseen"


def _on_server(path: str) -> Path | None:
    """The client's path as a path on the server's disk; ``None`` — not one the server can name:
    a relative path is the client's, and a home the server does not know is the client's too."""
    try:
        source = Path(path).expanduser()
    except RuntimeError:
        return None
    return source if source.is_absolute() else None


def _servers_own(source: Path) -> str | None:
    """What of the server's own ``source`` is, after its links are followed; ``None`` — not its.

    The kernel's views of the process (``/proc``, ``/sys``, ``/dev`` — the environment with its keys
    among them), this installation's ``runtime/`` (the database, the logs, the stored files), its
    ``.env*`` files, and wherever the settings moved the rest of its data: the SQLite file with its
    journal files, the stores' root, the folder of copies. A client asking for one of them through
    a path is asking the server to hand over its secrets; its own copy of a file it means it can
    still send by upload.
    """
    try:
        resolved = source.resolve()
    except (OSError, RuntimeError):
        return None
    if any(resolved.is_relative_to(root) for root in _SYSTEM_ROOTS):
        return "a system file"
    runtimes = {(project_root() / "runtime").resolve(), resolve_runtime_root().resolve()}
    if any(resolved.is_relative_to(runtime) for runtime in runtimes):
        return "the installation's runtime folder"
    if resolved.parent == project_root().resolve() and resolved.name.startswith(".env"):
        return "the installation's settings"
    config = get_config()
    database = config.sqlite_file
    if database is not None:
        database = database.resolve()
        if resolved.parent == database.parent and resolved.name.startswith(database.name):
            return "the installation's database"
        # The copies lie next to a file database; with any other they are under the runtime root.
        if resolved.is_relative_to(database.parent / BACKUP_FOLDER_NAME):
            return "the installation's copies"
    if resolved.is_relative_to(config.storage_root.resolve()):
        return "the installation's stored files"
    return None


def _reach(source: Path) -> tuple[_Reach, str]:
    """What the server finds at ``source`` and, for a file it may not open, why."""
    try:
        if not source.exists():
            return _Reach.UNSEEN, ""
        if not source.is_file():
            return _Reach.NOT_A_FILE, ""
    except OSError:
        # A folder on the way the server may not enter: whether anything is there is unknown
        # to it, so the file is treated as the client's, as an absent one is.
        return _Reach.UNSEEN, ""
    try:
        with source.open("rb"):
            pass
    except OSError as error:
        return _Reach.SEALED, error.strerror or str(error)
    return _Reach.READABLE, ""


def _locate(path: str) -> Path | None:
    source = _on_server(path)
    if source is None:
        return None
    own = _servers_own(source)
    if own is not None:
        raise ServersOwnFile(own)
    reach, reason = _reach(source)
    if reach is _Reach.NOT_A_FILE:
        raise NotAFile(str(source))
    if reach is _Reach.SEALED:
        raise UnreadableFile(reason)
    return source if reach is _Reach.READABLE else None


async def server_file(path: str) -> Path | None:
    """The readable file ``path`` names on the server's disk; ``None`` — the server cannot see
    one there, or reads no path at all (``server_path_enabled``), and the bytes have to be sent.
    ``ServersOwnFile``, ``NotAFile``, ``UnreadableFile`` — something is there and is not taken."""
    if not server_path_enabled():
        return None
    return await asyncio.to_thread(_locate, path)


def _opened(source: Path) -> BinaryIO:
    """``source`` opened, and proved after the opening to be a file the guard lets through.

    The path was checked when ``server_file`` found it, but a link on it may be pointed elsewhere
    before the server opens it. So the opened file itself is what is checked: the path is resolved
    again, refused if it is the server's own, and the file at its end must be the very one that
    was opened — a link swapped in between makes them two files.
    """
    try:
        handle = source.open("rb")
    except OSError as error:
        raise UnreadableFile(error.strerror or str(error)) from error
    try:
        resolved = source.resolve()
        own = _servers_own(resolved)
        if own is not None:
            raise ServersOwnFile(own)
        opened, there = os.fstat(handle.fileno()), os.stat(resolved)
        if not stat.S_ISREG(opened.st_mode):
            raise NotAFile(str(source))
        if (opened.st_dev, opened.st_ino) != (there.st_dev, there.st_ino):
            raise UnreadableFile("the file under the path changed while it was being opened")
    except OSError as error:
        handle.close()
        raise UnreadableFile(error.strerror or str(error)) from error
    except BaseException:
        handle.close()
        raise
    return handle


async def _chunks_of(handle: BinaryIO) -> AsyncIterator[bytes]:
    while chunk := await asyncio.to_thread(handle.read, CHUNK_SIZE):
        yield chunk


async def take_server_file(
    holder_code: str, source: Path, *, payload: Payload, workspace: str | None = None
) -> AttachedFile:
    """Hand the file at ``source`` to the holder, under the name it has there; the file stays.

    ``payload`` — what the client asks the holder for, handed over as is; ``workspace`` — the
    workspace of the agent naming the path: the holder asks its rights there too. Its name and the
    holder's checks are refused before it is opened; the opened file is checked again
    (``_opened``) and refused over the ceiling by its size; it is read into the storage's
    temporary file with no lock held, and the holder takes that.
    """
    name = kept_name(source.name)
    holder, bare = upload_holder(holder_code)
    await holder.check(bare, payload, workspace=workspace)
    handle = await asyncio.to_thread(_opened, source)
    try:
        refuse_oversize((await asyncio.to_thread(os.fstat, handle.fileno())).st_size)
        async with file_spool(_chunks_of(handle)) as spooled:
            return await holder.attach(bare, spooled, payload, filename=name, workspace=workspace)
    finally:
        await asyncio.to_thread(handle.close)


__all__ = ["server_file", "take_server_file"]
