"""A task's file from bytes, for the tests that need one in place before what they check.

The application takes bytes only through ``core_storage_upload``, which spools them and hands the
spooled file to ``task_file_attach_spooled``; this does the same two steps without a holder
registry, so a test of detaching, deleting or listing does not depend on the upload module.
"""

from __future__ import annotations

from collections.abc import AsyncIterator

from src.modules.core_storage.services.registration import file_spool
from src.modules.tasks import files as task_files
from src.modules.tasks.files import FilePlace
from src.modules.tasks.models.file import TasksFile


async def _chunks(data: bytes) -> AsyncIterator[bytes]:
    yield data


async def task_file_attach_bytes(
    task_code: str,
    data: bytes,
    *,
    filename: str = "",
    place: FilePlace = FilePlace(),
    title: str = "",
    description: str = "",
) -> TasksFile:
    async with file_spool(_chunks(data)) as spooled:
        return await task_files.task_file_attach_spooled(
            task_code,
            spooled,
            filename=filename,
            place=place,
            title=title,
            description=description,
        )


__all__ = ["task_file_attach_bytes"]
