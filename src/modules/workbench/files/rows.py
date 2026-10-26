"""A holder's files as its read lists them — code, title, description, in the holder's order.

A file the file manager deleted is left out, as every holder's own list leaves it out: for the rest
of the code it does not exist. Two queries per holder whatever the number of files.
"""

from __future__ import annotations

from collections.abc import Sequence

from src.modules.codex.crud import file as codex_file_crud
from src.modules.codex.models import CodexFile
from src.modules.core_storage.services.files import file_get_many
from src.modules.tasks.crud import file as task_file_crud
from src.modules.tasks.models.file import TasksFile
from src.modules.workbench.dto import AgentFileRow


async def task_file_rows(task_code: str) -> list[AgentFileRow]:
    return await _rows(await task_file_crud.task_file_list(task_code))


async def codex_note_file_rows(note_code: str) -> list[AgentFileRow]:
    return await _rows(await codex_file_crud.codex_file_list(note_code))


async def _rows(bindings: Sequence[TasksFile | CodexFile]) -> list[AgentFileRow]:
    if not bindings:
        return []
    stored = await file_get_many([row.file_code for row in bindings])
    return [
        AgentFileRow(code=row.file_code, title=row.title, description=row.description)
        for row in bindings
        if row.file_code in stored
    ]


__all__ = ["codex_note_file_rows", "task_file_rows"]
