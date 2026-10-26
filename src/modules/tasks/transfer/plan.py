"""The plan of a task import: the archive's rows checked, every entity judged — before a write.

Every entity tries to keep its code. A code taken here is a conflict, and what may be done about
it depends on what holds it:

- a task of THIS workspace — «update» or «replace»; of another — «replace» only: a task does not
  move between workspaces. A subtask follows its root: it may be updated only with the root.
- a note of the target task — «update» (with its task) or «replace»; a document of no task —
  either; a note of another task — «replace» only: a note belongs to one task.
- a file — by «code + sha256» (``core_transfer.files``): the same bytes are never a conflict; a
  code holding other bytes — «replace» only, the bytes here are shared and never change.
- a stage, a journal entry — no choice of their own: they follow their task, and one whose code
  another task holds gets a new code (a notice, not a question).

The plan reads only. The apply builds it again over the base as it is then (``runner.py``).
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from src.core.utils.date import datetime_to_agent
from src.modules.core_transfer.conflicts import Conflict, Side, both_ways, only_replace, plan_token
from src.modules.core_transfer.container import ArchiveReader
from src.modules.core_transfer.errors import ARCHIVE_INCONSISTENT, TransferError
from src.modules.core_transfer.files import (
    FILE_CONFLICT,
    FILE_RECODE,
    ArchivedFile,
    FileVerdict,
    judge_files,
    refuse_over_ceiling,
)
from src.modules.core_transfer.manifest import Manifest
from src.modules.core_transfer.rows import check_rows
from src.modules.notes.constants import BODY_MAX as NOTE_BODY_MAX
from src.modules.notes.models.note import Note
from src.modules.tasks.constants import (
    ACTOR_KINDS,
    FILE_CODE_PREFIX,
    FILE_STORE,
    JOURNAL_CODE_PREFIX,
    JOURNAL_TYPES,
    NOTE_CODE_PREFIX,
    STAGE_CODE_PREFIX,
    TASK_CODE_PREFIX,
    TASK_PRIORITIES,
    TASK_STATUSES,
    TASK_TYPES,
)
from src.modules.tasks.crud import transfer as transfer_crud
from src.modules.tasks.models.file import TasksFile
from src.modules.tasks.models.journal import TasksJournal
from src.modules.tasks.models.link import TasksLink
from src.modules.tasks.models.note import TasksNote
from src.modules.tasks.models.stage import TasksStage
from src.modules.tasks.models.task import TasksTask
from src.modules.tasks.transfer.constants import (
    ENTITY_FILES,
    ENTITY_JOURNAL,
    ENTITY_LINKS,
    ENTITY_NOTES,
    ENTITY_STAGES,
    ENTITY_TASKS,
    REASON_FILE_OTHER_CONTENT,
    REASON_NOTE_OTHER_TASK,
    REASON_TASK_OTHER_WORKSPACE,
    file_entry,
    note_body_entry,
    rows_entry,
)
from src.modules.workspace.crud.workspace import workspace_get

REASON_PARENT_REPLACED = "parent_replaced"
REASON_TASK_HAS_SUBTASKS = "task_has_subtasks"

_CODE = re.compile(r"^[0-9A-F]{10}$")
_SHA = re.compile(r"^[0-9a-f]{64}$")


def _inconsistent(detail: str) -> TransferError:
    return TransferError(ARCHIVE_INCONSISTENT, f"The archive contradicts itself: {detail}", params={"detail": detail})


def _code(value: Any, what: str) -> str:
    if not isinstance(value, str) or not _CODE.match(value):
        raise _inconsistent(f"{what} is not a code: {value!r}")
    return value


def _optional_code(value: Any, what: str) -> str | None:
    return None if value is None else _code(value, what)


def _one_of(value: Any, allowed: tuple[str, ...], what: str) -> str:
    if value not in allowed:
        raise _inconsistent(f"{what} {value!r} is not one of {list(allowed)}")
    return value


def _position(value: Any, what: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool):
        raise _inconsistent(f"{what} has no position: {value!r}")
    return value


def _stamp(value: datetime | None) -> str | None:
    return datetime_to_agent(value) if value is not None else None


@dataclass
class ArchiveContent:
    """The archive's rows, checked to hold together; ``tasks[0]`` is the root."""

    manifest: Manifest
    tasks: list[dict[str, Any]]
    links: dict[str, dict[str, Any]]
    stages: list[dict[str, Any]]
    journal: list[dict[str, Any]]
    notes: list[dict[str, Any]]
    files: list[dict[str, Any]]

    @property
    def root(self) -> dict[str, Any]:
        return self.tasks[0]

    def task_of_note(self) -> dict[str, str]:
        return {row["note"]["code"]: row["link"]["task_code"] for row in self.notes}

    def archived_files(self) -> dict[str, ArchivedFile]:
        """One per file code — a subtask holding the root's file shares the entry."""
        found: dict[str, ArchivedFile] = {}
        for row in self.files:
            code = row["binding"]["file_code"]
            found.setdefault(code, ArchivedFile(
                code=code,
                sha256=row["stored"]["sha256"],
                size=int(row["stored"]["size"]),
                entry=row["entry"],
                filename=str(row.get("name") or ""),
            ))
        return found


def read_content(reader: ArchiveReader) -> ArchiveContent:
    """The rows of an opened, verified archive, refused unless every reference stays inside."""
    manifest = reader.manifest or reader.open_manifest()
    tasks = reader.rows(rows_entry(ENTITY_TASKS))
    if not tasks or tasks[0].get("code") != manifest.root.code:
        raise _inconsistent("the first task is not the manifest's root")

    task_codes: set[str] = set()
    for row in tasks:
        code = _code(row.get("code"), "a task")
        if code in task_codes:
            raise _inconsistent(f"the task {code} comes twice")
        task_codes.add(code)
        _one_of(row.get("type"), TASK_TYPES, "task type")
        _one_of(row.get("status"), TASK_STATUSES, "task status")
        _one_of(row.get("priority"), TASK_PRIORITIES, "task priority")
        _one_of(row.get("created_by"), ACTOR_KINDS, "task author")
        if not str(row.get("title") or "").strip():
            raise _inconsistent(f"the task {code} has no title")

    root = tasks[0]["code"]
    links = {}
    for row in reader.rows(rows_entry(ENTITY_LINKS)):
        child = _code(row.get("task_code"), "a tree edge")
        if child == root or child not in task_codes or row.get("parent_code") != root:
            raise _inconsistent(f"the tree edge of {child} does not lead to the root")
        _position(row.get("sort"), f"the subtask {child}")
        links[child] = row
    if set(links) != task_codes - {root}:
        raise _inconsistent("a subtask has no tree edge")

    stages = reader.rows(rows_entry(ENTITY_STAGES))
    stage_task: dict[str, str] = {}
    numbers: set[tuple[str, int]] = set()
    for row in stages:
        code = _code(row.get("code"), "a stage")
        task = _code(row.get("task_code"), f"the task of stage {code}")
        if task not in task_codes or code in stage_task:
            raise _inconsistent(f"the stage {code} is not of an archived task or comes twice")
        number = row.get("number")
        if not isinstance(number, int) or (task, number) in numbers:
            raise _inconsistent(f"the stage {code} has a number taken or none")
        numbers.add((task, number))
        _one_of(row.get("status"), TASK_STATUSES, "stage status")
        stage_task[code] = task

    journal = reader.rows(rows_entry(ENTITY_JOURNAL))
    seen_entries: set[str] = set()
    for row in journal:
        code = _code(row.get("code"), "a journal entry")
        task = _code(row.get("task_code"), f"the task of entry {code}")
        stage = _optional_code(row.get("stage_code"), f"the stage of entry {code}")
        if task not in task_codes or code in seen_entries or (stage is not None and stage_task.get(stage) != task):
            raise _inconsistent(f"the journal entry {code} is not of an archived task")
        seen_entries.add(code)
        _one_of(row.get("type"), JOURNAL_TYPES, "journal entry type")

    notes = reader.rows(rows_entry(ENTITY_NOTES))
    note_task: dict[str, str] = {}
    for row in notes:
        link, note = row.get("link") or {}, row.get("note") or {}
        code = _code(note.get("code"), "a note")
        if link.get("note_code") != code or code in note_task:
            raise _inconsistent(f"the note {code} is not linked to its row or comes twice")
        task = _code(link.get("task_code"), f"the task of note {code}")
        _position(link.get("sort"), f"the note {code}")
        body = reader.inventory_of(note_body_entry(code))
        if task not in task_codes or body is None:
            raise _inconsistent(f"the note {code} is not of an archived task or has no body")
        # A body is at most NOTE_BODY_MAX characters, four bytes each at most: a larger entry is not
        # one this application wrote, and it is not read into memory.
        if body.bytes > 4 * NOTE_BODY_MAX:
            raise _inconsistent(f"the body of note {code} is larger than any body this application writes")
        if not str(note.get("title") or "").strip():
            raise _inconsistent(f"the note {code} has no title")
        note_task[code] = task

    files = reader.rows(rows_entry(ENTITY_FILES))
    pairs: set[tuple[str, str]] = set()
    content_of: dict[str, str] = {}
    code_of: dict[str, str] = {}
    for row in files:
        binding, stored = row.get("binding") or {}, row.get("stored") or {}
        code = _code(binding.get("file_code"), "a file")
        task = _code(binding.get("task_code"), f"the task of file {code}")
        note = _optional_code(binding.get("note_code"), f"the note of file {code}")
        stage = _optional_code(binding.get("stage_code"), f"the stage of file {code}")
        if task not in task_codes or (task, code) in pairs:
            raise _inconsistent(f"the file {code} is not of an archived task or comes twice in it")
        if (note is not None and note_task.get(note) != task) or (stage is not None and stage_task.get(stage) != task):
            raise _inconsistent(f"the place of file {code} is not of its task")
        if note is not None and stage is not None:
            raise _inconsistent(f"the file {code} names both a note and a stage")
        sha = stored.get("sha256")
        if not isinstance(sha, str) or not _SHA.match(sha) or content_of.setdefault(code, sha) != sha:
            raise _inconsistent(f"the file {code} has no content sum, or two")
        if code_of.setdefault(sha, code) != code:
            raise _inconsistent(f"one content comes under two codes, {code_of[sha]} and {code}")
        if row.get("entry") != file_entry(code, str(stored.get("extension") or "")) or not reader.has(row["entry"]):
            raise _inconsistent(f"the bytes of file {code} are not in the archive")
        size = stored.get("size")
        if not isinstance(size, int) or size < 0:
            raise _inconsistent(f"the file {code} has no size")
        # The sum a row claims decides which file here it takes by content: trusted only where it is
        # the sum of the bytes the archive carries, or a crafted row would take any file here.
        inventory = reader.inventory_of(row["entry"])
        if inventory is None or inventory.sha256 != sha or inventory.bytes != size:
            raise _inconsistent(f"the file {code} claims another content than its bytes")
        pairs.add((task, code))

    check_rows(TasksTask, tasks, omit=("workspace_code", "group_code"))
    check_rows(TasksLink, list(links.values()))
    check_rows(TasksStage, stages)
    check_rows(TasksJournal, journal)
    check_rows(Note, [row["note"] for row in notes], omit=("body", "deleted_at"))
    check_rows(TasksNote, [row["link"] for row in notes])
    check_rows(TasksFile, [row["binding"] for row in files])

    return ArchiveContent(
        manifest=manifest, tasks=tasks, links=links, stages=stages, journal=journal, notes=notes, files=files,
    )


@dataclass
class ImportPlan:
    """What will become of every entity, and what the person is to choose."""

    content: ArchiveContent
    workspace_code: str
    same_install: bool
    conflicts: list[Conflict]
    local_tasks: dict[str, TasksTask]
    local_notes: dict[str, tuple[Note, TasksNote | None]]
    local_stages: dict[str, TasksStage]
    local_journal: dict[str, TasksJournal]
    verdicts: dict[str, FileVerdict]
    recoded: list[dict[str, str]] = field(default_factory=list)

    @property
    def token(self) -> str:
        return plan_token(self.conflicts, (f"{r['entity']}:{r['from']}>{r['to']}" for r in self.recoded))

    def conflict(self, conflict_id: str) -> Conflict | None:
        return next((c for c in self.conflicts if c.id == conflict_id), None)


async def build_plan(reader: ArchiveReader, *, workspace_code: str, install: str) -> ImportPlan:
    content = read_content(reader)
    task_codes = [row["code"] for row in content.tasks]
    local_tasks = await transfer_crud.rows_by_codes(TasksTask, task_codes)
    local_notes = await transfer_crud.notes_by_codes(row["note"]["code"] for row in content.notes)
    local_stages = await transfer_crud.rows_by_codes(TasksStage, (row["code"] for row in content.stages))
    local_journal = await transfer_crud.rows_by_codes(TasksJournal, (row["code"] for row in content.journal))
    verdicts = await judge_files(content.archived_files().values(), store=FILE_STORE)
    refuse_over_ceiling(verdicts.values())

    titles = await _workspace_titles(task.workspace_code for task in local_tasks.values())
    conflicts: list[Conflict] = []
    task_conflict: dict[str, Conflict] = {}

    root_code = content.root["code"]
    for row in content.tasks:
        local = local_tasks.get(row["code"])
        if local is None:
            continue
        conflict = await _task_conflict(row, local, workspace_code, titles,
                                        root=task_conflict.get(root_code), is_root=row["code"] == root_code)
        task_conflict[row["code"]] = conflict
        conflicts.append(conflict)

    holder_titles = await _task_titles(
        link.task_code for _, link in local_notes.values() if link is not None
    )
    for row in content.notes:
        code = row["note"]["code"]
        if code not in local_notes:
            continue
        conflicts.append(_note_conflict(row, local_notes[code], task_conflict, holder_titles))

    for code, verdict in verdicts.items():
        if verdict.outcome == FILE_CONFLICT:
            conflicts.append(_file_conflict(code, verdict, content))

    recoded = _definite_recodes(content, local_stages, local_journal, verdicts)

    return ImportPlan(
        content=content,
        workspace_code=workspace_code,
        same_install=bool(content.manifest.source.install_id) and content.manifest.source.install_id == install,
        conflicts=conflicts,
        local_tasks=local_tasks,
        local_notes=local_notes,
        local_stages=local_stages,
        local_journal=local_journal,
        verdicts=verdicts,
        recoded=recoded,
    )


async def _task_conflict(row, local: TasksTask, workspace_code: str, titles: dict[str, str], *,
                         root: Conflict | None, is_root: bool) -> Conflict:
    conflict_id = f"{TASK_CODE_PREFIX}@{row['code']}"
    entity = "task" if is_root else "subtask"
    here = Side(updated_at=_stamp(local.updated_at), created_at=_stamp(local.created_at))
    archive = Side(updated_at=row.get("updated_at"), created_at=row.get("created_at"))
    described = {
        "kind": "task",
        "code": conflict_id,
        "title": local.title,
        "workspace": titles.get(local.workspace_code, ""),
        "deleted": "1" if local.deleted_at is not None else "",
    }
    if local.workspace_code != workspace_code:
        return only_replace(conflict_id, entity, row["title"], described, here=here, archive=archive,
                            reason=REASON_TASK_OTHER_WORKSPACE,
                            reason_params={"workspace": titles.get(local.workspace_code, "")})
    if not is_root:
        if root is not None and "update" not in root.options:
            return only_replace(conflict_id, entity, row["title"], described, here=here, archive=archive,
                                reason=REASON_PARENT_REPLACED)
        if await transfer_crud.live_children(local.code):
            return only_replace(conflict_id, entity, row["title"], described, here=here, archive=archive,
                                reason=REASON_TASK_HAS_SUBTASKS)
        requires = (root.id, "update") if root is not None else None
        return both_ways(conflict_id, entity, row["title"], described, here=here, archive=archive, requires=requires)
    return both_ways(conflict_id, entity, row["title"], described, here=here, archive=archive)


def _note_conflict(row, local: tuple[Note, TasksNote | None], task_conflict: dict[str, Conflict],
                   holder_titles: dict[str, str]) -> Conflict:
    note, link = local
    code = row["note"]["code"]
    archive_task = row["link"]["task_code"]
    conflict_id = f"{NOTE_CODE_PREFIX}@{code}"
    here = Side(updated_at=_stamp(note.updated_at), created_at=_stamp(note.created_at))
    archive = Side(updated_at=row["note"].get("updated_at"), created_at=row["note"].get("created_at"))
    described = {
        "kind": "note",
        "code": conflict_id,
        "title": note.title,
        "holder": f"{TASK_CODE_PREFIX}@{link.task_code}" if link is not None else "",
        "holder_title": holder_titles.get(link.task_code, "") if link is not None else "",
        "deleted": "1" if note.deleted_at is not None else "",
    }
    title = row["note"]["title"]
    if link is None:
        return both_ways(conflict_id, "note", title, described, here=here, archive=archive)
    holder = task_conflict.get(link.task_code) if link.task_code == archive_task else None
    if holder is None or "update" not in holder.options:
        return only_replace(conflict_id, "note", title, described, here=here, archive=archive,
                            reason=REASON_NOTE_OTHER_TASK,
                            reason_params={"task": described["holder"], "title": described["holder_title"]})
    return both_ways(conflict_id, "note", title, described, here=here, archive=archive,
                     requires=(holder.id, "update"))


def _file_conflict(code: str, verdict: FileVerdict, content: ArchiveContent) -> Conflict:
    row = next(row for row in content.files if row["binding"]["file_code"] == code)
    local = verdict.local
    conflict_id = f"{FILE_CODE_PREFIX}@{code}"
    title = row["binding"].get("title") or row.get("name") or conflict_id
    return only_replace(
        conflict_id,
        "file",
        title,
        {"kind": "file", "code": conflict_id, "title": "", "mime": local.mime if local else ""},
        here=Side(created_at=_stamp(local.created_at) if local else None, size=local.size if local else None),
        archive=Side(
            updated_at=row["binding"].get("updated_at"),
            created_at=row["stored"].get("created_at"),
            size=int(row["stored"]["size"]),
        ),
        reason=REASON_FILE_OTHER_CONTENT,
    )


def _definite_recodes(content: ArchiveContent, local_stages, local_journal,
                      verdicts: dict[str, FileVerdict]) -> list[dict[str, str]]:
    """What changes its code whatever the person chooses: a stage or an entry whose code another
    task holds, a file whose content is here under another code."""
    found: list[dict[str, str]] = []
    for entity, prefix, rows, local in (
        ("stage", STAGE_CODE_PREFIX, content.stages, local_stages),
        ("journal", JOURNAL_CODE_PREFIX, content.journal, local_journal),
    ):
        for row in rows:
            held = local.get(row["code"])
            if held is not None and held.task_code != row["task_code"]:
                found.append({"entity": entity, "title": row["title"], "from": f"{prefix}@{row['code']}", "to": ""})
    for code, verdict in verdicts.items():
        if verdict.outcome == FILE_RECODE and verdict.local is not None:
            row = next(row for row in content.files if row["binding"]["file_code"] == code)
            found.append({
                "entity": "file",
                "title": row["binding"].get("title") or row.get("name") or "",
                "from": f"{FILE_CODE_PREFIX}@{code}",
                "to": f"{FILE_CODE_PREFIX}@{verdict.local.code}",
            })
    return found


async def _workspace_titles(codes: Iterable[str]) -> dict[str, str]:
    titles: dict[str, str] = {}
    for code in set(codes):
        workspace = await workspace_get(code, include_deleted=True)
        titles[code] = workspace.title if workspace is not None else ""
    return titles


async def _task_titles(codes: Iterable[str]) -> dict[str, str]:
    return {code: row.title for code, row in (await transfer_crud.rows_by_codes(TasksTask, codes)).items()}


def plan_body(plan: ImportPlan, *, file_name: str, size: int) -> dict[str, Any]:
    """The plan as the interface reads it."""
    manifest = plan.content.manifest
    return {
        "archive": {
            "file_name": file_name,
            "size": size,
            "created_at": manifest.created_at,
            "app_version": manifest.source.app_version,
            "format_version": manifest.format_version,
            "same_install": plan.same_install,
            "source_workspace": manifest.source.extra.get("workspace_title", ""),
        },
        "root": {
            "code": f"{TASK_CODE_PREFIX}@{plan.content.root['code']}",
            "title": plan.content.root["title"],
            "subtasks": len(plan.content.tasks) - 1,
        },
        "counts": {
            "tasks": len(plan.content.tasks),
            "stages": len(plan.content.stages),
            "journal": len(plan.content.journal),
            "notes": len(plan.content.notes),
            "files": len(plan.content.archived_files()),
        },
        "conflicts": [conflict.as_dict() for conflict in plan.conflicts],
        "notices": {
            "recoded": plan.recoded,
            "dangling_refs": list(manifest.dangling_refs),
        },
        "plan_token": plan.token,
    }


__all__ = [
    "ArchiveContent",
    "ImportPlan",
    "REASON_PARENT_REPLACED",
    "REASON_TASK_HAS_SUBTASKS",
    "build_plan",
    "plan_body",
    "read_content",
]
