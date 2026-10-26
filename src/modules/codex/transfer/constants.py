"""The ``.ucdx`` format: its type, its entries, the references its texts carry."""

from __future__ import annotations

import re

from src.modules.codex.constants import CODEX_CODE_PREFIX, FILE_CODE_PREFIX
from src.modules.core_transfer.container import ArchiveFormat
from src.modules.core_transfer.refs import ReferenceScheme

ENTITY_CODEX = "codex"
ENTITY_NOTES = "notes"
ENTITY_FILES = "files"
ROW_ENTITIES = (ENTITY_CODEX, ENTITY_NOTES, ENTITY_FILES)

_CODE = r"[0-9A-F]{10}"

CODEX_ARCHIVE = ArchiveFormat(
    media_type="application/vnd.uroboros.codex+zip",
    name="uroboros.codex",
    version=1,
    extension=".ucdx",
    entries=(
        re.compile(rf"rows/({'|'.join(ROW_ENTITIES)})\.jsonl"),
        re.compile(rf"bodies/(codex|notes)/{_CODE}\.md"),
        re.compile(rf"files/{_CODE}(\.[a-z0-9]{{1,15}})?"),
    ),
)

UPLOAD_CONSUMER = "codex"
IMAGE_WORD = "IMAGE"


def rows_entry(entity: str) -> str:
    return f"rows/{entity}.jsonl"


def codex_body_entry(code: str) -> str:
    return f"bodies/codex/{code}.md"


def note_body_entry(code: str) -> str:
    return f"bodies/notes/{code}.md"


def file_entry(code: str, extension: str) -> str:
    return f"files/{code}{extension}"


# A codex and its records share one word and one code space.
REFERENCES = ReferenceScheme([CODEX_CODE_PREFIX, FILE_CODE_PREFIX], aliases={IMAGE_WORD: FILE_CODE_PREFIX})

OUTSIDE_REFERENCES = ReferenceScheme(
    [CODEX_CODE_PREFIX, FILE_CODE_PREFIX, "TASK", "STAGE", "JOURNAL", "NOTE", "TASKGROUP", "WORKSPACE"],
    aliases={IMAGE_WORD: FILE_CODE_PREFIX, "GROUP": "TASKGROUP"},
)

CODEX_TEXTS = ("title", "description")
NOTE_TEXTS = ("title", "description")
FILE_TEXTS = ("title", "description")

# Why an «update» is not offered — keys of the interface's dictionary (``codex.transfer.reason.*``).
REASON_CODE_IS_RECORD = "code_is_record"
REASON_CODE_IS_CODEX = "code_is_codex"
REASON_RECORD_OTHER_CODEX = "record_other_codex"
REASON_PARENT_REPLACED = "parent_replaced"
REASON_DEPTH_EXCEEDED = "depth_exceeded"
REASON_FILE_OTHER_CONTENT = "file_other_content"

__all__ = [
    "CODEX_ARCHIVE",
    "CODEX_TEXTS",
    "ENTITY_CODEX",
    "ENTITY_FILES",
    "ENTITY_NOTES",
    "FILE_TEXTS",
    "NOTE_TEXTS",
    "OUTSIDE_REFERENCES",
    "REASON_CODE_IS_CODEX",
    "REASON_CODE_IS_RECORD",
    "REASON_DEPTH_EXCEEDED",
    "REASON_FILE_OTHER_CONTENT",
    "REASON_PARENT_REPLACED",
    "REASON_RECORD_OTHER_CODEX",
    "REFERENCES",
    "ROW_ENTITIES",
    "UPLOAD_CONSUMER",
    "codex_body_entry",
    "file_entry",
    "note_body_entry",
    "rows_entry",
]
