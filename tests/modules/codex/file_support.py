"""A codex note's file from bytes, for the tests that need one in place before what they check.

The application takes bytes only through ``core_storage_upload``, which spools them and hands the
spooled file to ``codex_file_attach_spooled``; this does the same two steps without a holder
registry, so a test of detaching or listing does not depend on the upload module.
"""

from __future__ import annotations

from collections.abc import AsyncIterator

from src.modules.codex import files as codex_files
from src.modules.codex.models import CodexFile
from src.modules.core_storage.services.registration import file_spool


async def _chunks(data: bytes) -> AsyncIterator[bytes]:
    yield data


async def codex_file_attach_bytes(
    note_code: str, data: bytes, *, filename: str = "", title: str = "", description: str = ""
) -> CodexFile:
    async with file_spool(_chunks(data)) as spooled:
        return await codex_files.codex_file_attach_spooled(
            note_code, spooled, filename=filename, title=title, description=description
        )


__all__ = ["codex_file_attach_bytes"]
