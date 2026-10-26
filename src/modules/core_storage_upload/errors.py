"""Refusals of the upload, and the codes the person's interface words them by.

A body over the ceiling is the storage's own ``FileTooLarge``: one refusal per meaning, whichever
layer finds it. A holder's refusal is the holder's — its code and its text travel as they are,
wrapped in ``HolderRefused`` with the kind of answer it is, since this module knows no holder's
rules and cannot tell a missing task from a deleted one by itself.

The codes ``core_storage_upload.<entity>.<reason>`` are read by the interface's dictionary
(``web/src/features/core_storage_upload/locales``); ``curl`` reads the English text next to them.
"""

from __future__ import annotations

from enum import Enum

from src.modules.core_storage_upload.dto import AttachedFile

REQUEST_UNAUTHORIZED = "core_storage_upload.request.unauthorized"
"""Neither the person's page (an ``Origin`` the app allows) nor an upload request's token."""
REQUEST_NOT_FOUND = "core_storage_upload.request.not_found"
"""No open upload request under this token: never opened, expired, completed, or taken by an
upload in flight — one answer for all four."""
REQUEST_FOREIGN_HOLDER = "core_storage_upload.request.foreign_holder"
"""The PUT names a holder other than the one the request was opened for."""
HOLDER_UNKNOWN = "core_storage_upload.holder.unknown"
"""The code names nothing that takes a file: no holder registered its prefix, or the code is empty."""
FILENAME_CONTROL_CHARACTER = "core_storage_upload.filename.control_character"
"""The file's name holds a control character — a name is one line of printable text."""
FILENAME_TOO_LONG = "core_storage_upload.filename.too_long"
"""The file's name is wider than the storage keeps (``core_storage`` ``ORIGINAL_FILENAME_MAX``)."""
FILE_TOO_LARGE = "core_storage_upload.file.too_large"
"""The body is over the storage's size ceiling (``core_storage`` setting ``max_file_size_mb``)."""


class UploadError(Exception):
    """Base of every refusal of this module."""


class UnknownHolder(UploadError, ValueError):
    """``holder`` is no code a registered holder reads."""

    def __init__(self, holder: str, known: list[str]) -> None:
        words = " / ".join(f"{prefix}@" for prefix in known) or "no holder is registered"
        super().__init__(f"{holder!r} names nothing that takes a file — pass a {words} code")
        self.holder = holder


class FilenameRefused(UploadError, ValueError):
    """A name the storage could not keep for the file (``core_storage.names.split_filename``) —
    found before the body is read. ``code`` says which rule it broke."""

    def __init__(self, message: str, *, code: str) -> None:
        super().__init__(message)
        self.code = code


class RequestNotFound(UploadError):
    """No open upload request under this token. One refusal for every reason — the answer must not
    tell a live token from a guessed one."""

    def __init__(self) -> None:
        super().__init__(
            "No open upload request under this address — ask attach_file for a new one"
        )


class RequestForeignHolder(UploadError):
    """The PUT names a holder other than its request's; the request stays open."""

    def __init__(self, request_holder: str, named: str) -> None:
        super().__init__(f"The upload address was opened for {request_holder}, not for {named}")


class RefusalKind(Enum):
    """What a holder's refusal means for the one who asked — the status an HTTP answer takes."""

    MISSING = "missing"
    CONFLICT = "conflict"
    FORBIDDEN = "forbidden"
    INVALID = "invalid"


class HolderRefused(UploadError, ValueError):
    """The holder said no — its own text, code and ``params``, and the kind of refusal it is.

    A ``ValueError`` like the holders' own refusals, so a caller that words those for its reader
    (the agent surface) words this one the same way, by its text.
    """

    def __init__(
        self,
        message: str,
        *,
        kind: RefusalKind,
        code: str | None = None,
        params: dict[str, str | int] | None = None,
    ) -> None:
        super().__init__(message)
        self.kind = kind
        self.code = code
        self.params = params or {}


class AlreadyHeld(HolderRefused):
    """The holder holds these very bytes already — ``attached`` is that file, as it is there.

    The person's page shows it as a calm notice (409 with the file in ``params``); an upload
    request completed with bytes the holder has already answers with that file.
    """

    def __init__(
        self,
        message: str,
        *,
        attached: AttachedFile,
        code: str | None = None,
        params: dict[str, str | int] | None = None,
    ) -> None:
        super().__init__(message, kind=RefusalKind.CONFLICT, code=code, params=params)
        self.attached = attached


class ServerFileRefused(UploadError):
    """A path on the server's disk that is not taken. Not a ``ValueError`` on purpose: the caller
    words it for its reader — this module does not know who asked or what else they may do."""


class ServersOwnFile(ServerFileRefused):
    """The path is the server's own (``reason`` says whose): the kernel's views of the process,
    the installation's ``runtime/``, its ``.env*`` files."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


class NotAFile(ServerFileRefused):
    """Something is there, but not a file — a folder, a socket."""


class UnreadableFile(ServerFileRefused):
    """A file the server sees and may not open; ``reason`` is the system's word for it."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


__all__ = [
    "FILENAME_CONTROL_CHARACTER",
    "FILENAME_TOO_LONG",
    "FILE_TOO_LARGE",
    "HOLDER_UNKNOWN",
    "REQUEST_FOREIGN_HOLDER",
    "REQUEST_NOT_FOUND",
    "REQUEST_UNAUTHORIZED",
    "AlreadyHeld",
    "FilenameRefused",
    "HolderRefused",
    "NotAFile",
    "RefusalKind",
    "RequestForeignHolder",
    "RequestNotFound",
    "ServerFileRefused",
    "ServersOwnFile",
    "UnknownHolder",
    "UnreadableFile",
    "UploadError",
]
