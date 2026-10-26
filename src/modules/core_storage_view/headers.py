"""The headers a served file goes out with.

- ``X-Content-Type-Options: nosniff`` on every file: the browser takes the stored type as given
  and never guesses a script out of a text file.
- ``Content-Security-Policy: sandbox`` on types that can run script (``constants.SANDBOXED_*``):
  the files come from the app's own origin, and a script in an uploaded SVG would otherwise act
  with the app's rights.
- ``Content-Disposition`` with the original name per RFC 6266 / RFC 5987: ``filename*`` carries
  the name in UTF-8, ``filename`` an ASCII fallback. A non-ASCII byte in a bare ``filename``
  breaks the response.
- ``ETag`` is the sha256 of the bytes with ``Cache-Control: no-cache``: the bytes under a code
  never change, but a soft-deleted file must stop being served at once, so the browser asks every
  time and a match costs a 304 without the bytes.
"""

from __future__ import annotations

from urllib.parse import quote

from src.modules.core_storage_view.constants import SANDBOXED_MIMES, SANDBOXED_SUFFIX
from src.modules.core_storage_view.dto import ServedFile

# ``"`` and ``\`` end or escape the quoted string; ``%`` some browsers decode in a bare
# ``filename``. A name holding any of them goes out only through ``filename*``.
_UNSAFE_IN_QUOTED = frozenset('"\\%')


def is_sandboxed(mime: str) -> bool:
    base = mime.split(";", 1)[0].strip().lower()
    return base in SANDBOXED_MIMES or base.endswith(SANDBOXED_SUFFIX)


def content_disposition(filename: str, fallback: str, *, download: bool) -> str:
    """``inline`` opens the file in the tab, ``attachment`` saves it; ``fallback`` — the ASCII
    name for a client that does not read ``filename*``, used when ``filename`` is not plain ASCII."""
    kind = "attachment" if download else "inline"
    plain = filename if _is_plain_ascii(filename) else fallback
    return f"{kind}; filename=\"{plain}\"; filename*=UTF-8''{quote(filename, safe='')}"


def etag(sha256: str) -> str:
    return f'"{sha256}"'


def etag_matches(if_none_match: str | None, current: str) -> bool:
    """``If-None-Match`` names the current tag: a list, weak tags and ``*`` included."""
    if not if_none_match:
        return False
    for candidate in if_none_match.split(","):
        candidate = candidate.strip()
        if candidate == "*" or candidate.removeprefix("W/") == current:
            return True
    return False


def file_headers(file: ServedFile, *, download: bool) -> dict[str, str]:
    headers = {
        "X-Content-Type-Options": "nosniff",
        "Cache-Control": "no-cache",
        "ETag": etag(file.sha256),
        "Content-Disposition": content_disposition(
            file.filename, f"{file.code}{file.extension}", download=download
        ),
    }
    if is_sandboxed(file.mime):
        headers["Content-Security-Policy"] = "sandbox"
    return headers


def _is_plain_ascii(name: str) -> bool:
    return bool(name) and all(" " <= char <= "~" and char not in _UNSAFE_IN_QUOTED for char in name)


__all__ = ["content_disposition", "etag", "etag_matches", "file_headers", "is_sandboxed"]
