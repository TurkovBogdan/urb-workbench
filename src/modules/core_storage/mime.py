"""What a file is: its mime, the extension it is stored under and its category.

There are no content detectors here — the security layer lives outside the module — so the type
is found in three steps: the byte signature (``filetype``) for binary formats, then the
extension of the name for formats without a signature (text, markdown, csv), else unknown.
The signature goes first, so a png named ``.md`` is still stored as an image.

The extension on disk comes from the found mime, not from the name the caller brought: a name
that lies about the content does not decide what the file is stored as.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import PurePath

import filetype

from src.modules.core_storage.constants import EXTENSION_MAX, FILE_TYPE_OTHER, UNKNOWN_MIME

# mime → (extension, category). Listed formats are the ones a workbench actually meets; anything
# else still gets a category from its mime family below.
_CATALOG: dict[str, tuple[str, str]] = {
    "image/png": ("png", "image"),
    "image/jpeg": ("jpg", "image"),
    "image/gif": ("gif", "image"),
    "image/webp": ("webp", "image"),
    "image/bmp": ("bmp", "image"),
    "image/svg+xml": ("svg", "image"),
    "image/x-icon": ("ico", "image"),
    "application/pdf": ("pdf", "document"),
    "application/msword": ("doc", "document"),
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": ("docx", "document"),
    "application/vnd.oasis.opendocument.text": ("odt", "document"),
    "application/rtf": ("rtf", "document"),
    "text/csv": ("csv", "table"),
    "application/vnd.ms-excel": ("xls", "table"),
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": ("xlsx", "table"),
    "application/vnd.oasis.opendocument.spreadsheet": ("ods", "table"),
    "application/vnd.ms-powerpoint": ("ppt", "presentation"),
    "application/vnd.openxmlformats-officedocument.presentationml.presentation": ("pptx", "presentation"),
    "application/vnd.oasis.opendocument.presentation": ("odp", "presentation"),
    "text/plain": ("txt", "text"),
    "text/markdown": ("md", "text"),
    "application/json": ("json", "text"),
    "application/yaml": ("yaml", "text"),
    "application/xml": ("xml", "text"),
    "text/html": ("html", "text"),
    "text/calendar": ("ics", "text"),
    "application/zip": ("zip", "archive"),
    "application/gzip": ("gz", "archive"),
    "application/x-tar": ("tar", "archive"),
    "application/x-7z-compressed": ("7z", "archive"),
    "application/x-rar-compressed": ("rar", "archive"),
    "video/mp4": ("mp4", "video"),
    "video/quicktime": ("mov", "video"),
    "video/webm": ("webm", "video"),
    "video/x-matroska": ("mkv", "video"),
    "font/woff": ("woff", "font"),
    "font/woff2": ("woff2", "font"),
    "font/ttf": ("ttf", "font"),
    "font/otf": ("otf", "font"),
    "application/vnd.ms-fontobject": ("eot", "font"),
    "application/pgp-keys": ("asc", "key"),
    "application/pkcs7-signature": ("p7s", "key"),
    "message/rfc822": ("eml", "email"),
    "application/vnd.ms-outlook": ("msg", "email"),
}

# Extensions of the formats without a byte signature, and spellings the catalog keys miss.
_MIME_BY_EXTENSION: dict[str, str] = {
    **{extension: mime for mime, (extension, _) in _CATALOG.items()},
    "jpeg": "image/jpeg",
    "markdown": "text/markdown",
    "log": "text/plain",
    "text": "text/plain",
    "yml": "application/yaml",
    "htm": "text/html",
}

# A mime family names the category of a type the catalog does not list.
_TYPE_BY_FAMILY = {"image": "image", "video": "video", "text": "text", "font": "font"}


@dataclass(frozen=True)
class Detected:
    mime: str
    extension: str
    type: str


def detect(head: bytes, filename: str) -> Detected:
    """The type of a file from its first bytes and, failing a signature, the extension of its name."""
    kind = filetype.guess(head) if head else None
    if kind is not None:
        mime = kind.mime
    else:
        mime = _MIME_BY_EXTENSION.get(PurePath(filename).suffix.lower().lstrip("."), UNKNOWN_MIME)

    listed = _CATALOG.get(mime)
    if listed is not None:
        extension, category = listed
    else:
        extension = kind.extension if kind is not None else ""
        category = _TYPE_BY_FAMILY.get(mime.split("/", 1)[0], FILE_TYPE_OTHER)

    dotted = f".{extension}" if extension and len(extension) < EXTENSION_MAX else ""
    return Detected(mime=mime, extension=dotted, type=category)


__all__ = ["Detected", "detect"]
