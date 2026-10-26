"""The ``.utsk`` format: its type, its entries, the references its texts carry.

One source for the writer, the reader and the plan: a line differing between export and import is
an archive the application cannot read back.
"""

from __future__ import annotations

import re

from src.modules.core_transfer.container import ArchiveFormat
from src.modules.core_transfer.refs import ReferenceScheme
from src.modules.tasks.constants import (
    FILE_CODE_PREFIX,
    GROUP_CODE_PREFIX,
    JOURNAL_CODE_PREFIX,
    NOTE_CODE_PREFIX,
    STAGE_CODE_PREFIX,
    TASK_CODE_PREFIX,
)

ENTITY_TASKS = "tasks"
ENTITY_LINKS = "links"
ENTITY_STAGES = "stages"
ENTITY_JOURNAL = "journal"
ENTITY_NOTES = "notes"
ENTITY_FILES = "files"
ROW_ENTITIES = (ENTITY_TASKS, ENTITY_LINKS, ENTITY_STAGES, ENTITY_JOURNAL, ENTITY_NOTES, ENTITY_FILES)

_CODE = r"[0-9A-F]{10}"

TASK_ARCHIVE = ArchiveFormat(
    media_type="application/vnd.uroboros.task+zip",
    name="uroboros.task",
    version=1,
    extension=".utsk",
    entries=(
        re.compile(rf"rows/({'|'.join(ROW_ENTITIES)})\.jsonl"),
        re.compile(rf"bodies/notes/{_CODE}\.md"),
        re.compile(rf"files/{_CODE}(\.[a-z0-9]{{1,15}})?"),
    ),
)

UPLOAD_CONSUMER = "tasks"


def rows_entry(entity: str) -> str:
    return f"rows/{entity}.jsonl"


def note_body_entry(code: str) -> str:
    return f"bodies/notes/{code}.md"


def file_entry(code: str, extension: str) -> str:
    return f"files/{code}{extension}"


IMAGE_WORD = "IMAGE"

# The words whose codes an import carries over: the archive holds each of these entities.
REFERENCES = ReferenceScheme(
    [TASK_CODE_PREFIX, STAGE_CODE_PREFIX, JOURNAL_CODE_PREFIX, NOTE_CODE_PREFIX, FILE_CODE_PREFIX],
    aliases={IMAGE_WORD: FILE_CODE_PREFIX},
)

# Every word a text may point out of the archive with — named in the manifest, never followed.
OUTSIDE_REFERENCES = ReferenceScheme(
    [
        TASK_CODE_PREFIX,
        STAGE_CODE_PREFIX,
        JOURNAL_CODE_PREFIX,
        NOTE_CODE_PREFIX,
        FILE_CODE_PREFIX,
        GROUP_CODE_PREFIX,
        "CODEX",
        "WORKSPACE",
    ],
    aliases={IMAGE_WORD: FILE_CODE_PREFIX, "GROUP": GROUP_CODE_PREFIX},
)

# The fields where a reference means a reference — what a person or the agent wrote.
TASK_TEXTS = ("title", "description", "context", "constraints", "criteria", "plan", "progress", "result")
STAGE_TEXTS = ("title", "description", "body", "evidence")
JOURNAL_TEXTS = ("title", "body", "resolution")
NOTE_TEXTS = ("title", "description")
FILE_TEXTS = ("title", "description")

# Why an «update» is not offered — keys of the interface's dictionary (``tasks.transfer.reason.*``).
REASON_TASK_OTHER_WORKSPACE = "task_other_workspace"
REASON_NOTE_OTHER_TASK = "note_other_task"
REASON_FILE_OTHER_CONTENT = "file_other_content"

__all__ = [
    "ENTITY_FILES",
    "ENTITY_JOURNAL",
    "ENTITY_LINKS",
    "ENTITY_NOTES",
    "ENTITY_STAGES",
    "ENTITY_TASKS",
    "FILE_TEXTS",
    "IMAGE_WORD",
    "JOURNAL_TEXTS",
    "NOTE_TEXTS",
    "OUTSIDE_REFERENCES",
    "REASON_FILE_OTHER_CONTENT",
    "REASON_NOTE_OTHER_TASK",
    "REASON_TASK_OTHER_WORKSPACE",
    "REFERENCES",
    "ROW_ENTITIES",
    "STAGE_TEXTS",
    "TASK_ARCHIVE",
    "TASK_TEXTS",
    "UPLOAD_CONSUMER",
    "file_entry",
    "note_body_entry",
    "rows_entry",
]
