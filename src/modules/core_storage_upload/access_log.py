"""The token of an upload request stays out of the server's access log.

The token rides in the address (``/storage/upload?token=…``), and uvicorn writes every request
line to its access log — a permission to upload, readable by anyone who reads the log, until the
request expires. The filter blanks the token's value in the lines of this module's route before
they are written; the rest of the line stays as it was.
"""

from __future__ import annotations

import logging
import re

from src.core.router.storage import STORAGE_PREFIX
from src.modules.core_storage_upload.constants import ROUTER_PREFIX, UPLOAD_ROUTE

ACCESS_LOGGER = "uvicorn.access"

_ROUTE = f"{STORAGE_PREFIX}{ROUTER_PREFIX}{UPLOAD_ROUTE}"
_TOKEN = re.compile(r"(?<=[?&]token=)[^&\s]*")


def _redacted(value: object) -> object:
    if isinstance(value, str) and value.startswith(_ROUTE):
        return _TOKEN.sub("***", value)
    return value


class RedactUploadTokens(logging.Filter):
    """Blanks ``token=`` in a request line of the upload route; never drops a record."""

    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.args, tuple):
            record.args = tuple(_redacted(arg) for arg in record.args)
        return True


def redact_access_log() -> None:
    """Put the filter on the access logger once per process."""
    logger = logging.getLogger(ACCESS_LOGGER)
    if not any(isinstance(existing, RedactUploadTokens) for existing in logger.filters):
        logger.addFilter(RedactUploadTokens())


__all__ = ["ACCESS_LOGGER", "RedactUploadTokens", "redact_access_log"]
