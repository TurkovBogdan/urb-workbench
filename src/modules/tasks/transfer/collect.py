"""Export of a task into a ``.utsk`` archive — reading only, the file written as a stream.

What goes: the task; when it is a top-level one, its live subtasks; their stages, journal, live
notes, and the files they hold — the binding rows and the bytes. What does not: the group and the
workspace (the import asks for them), the tree edge of the root (the import places it), deleted
subtasks and notes. A file whose place was a note left behind stays in the task without a place.

References out of the archive — to other tasks, groups, codexes — are not followed: that would
drag half the base along. They are named in the manifest instead.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ulid import ULID

from src.core.utils.date import datetime_to_agent
from src.core.version import app_version
from src.modules.core_storage.services.files import file_path
from src.modules.core_transfer.container import ArchiveWriter
from src.modules.core_transfer.install import install_id
from src.modules.core_transfer.manifest import Manifest, ManifestRoot, ManifestSource
from src.modules.core_transfer.naming import archive_file_name
from src.modules.core_transfer.rows import row_to_json
from src.modules.tasks.constants import (
    FILE_CODE_PREFIX,
    JOURNAL_CODE_PREFIX,
    NOTE_CODE_PREFIX,
    STAGE_CODE_PREFIX,
    TASK_CODE_PREFIX,
)
from src.modules.tasks.crud import task as task_crud
from src.modules.tasks.crud import transfer as transfer_crud
from src.modules.tasks.files import task_file_views
from src.modules.tasks.transfer.constants import (
    ENTITY_FILES,
    ENTITY_JOURNAL,
    ENTITY_LINKS,
    ENTITY_NOTES,
    ENTITY_STAGES,
    ENTITY_TASKS,
    FILE_TEXTS,
    JOURNAL_TEXTS,
    NOTE_TEXTS,
    OUTSIDE_REFERENCES,
    STAGE_TEXTS,
    TASK_ARCHIVE,
    TASK_TEXTS,
    file_entry,
    note_body_entry,
    rows_entry,
)
from src.modules.workspace.crud.workspace import workspace_get

_TASK_OMITTED = ("workspace_code", "group_code")


@dataclass(frozen=True)
class ExportedArchive:
    path: Path
    file_name: str
    manifest: Manifest


async def export_task(code: str, path: Path) -> ExportedArchive:
    """Write the archive of a live task at ``path``; ``LookupError`` — no such live task."""
    root = await task_crud.task_get(code)
    if root is None:
        raise LookupError(code)

    root_link = (await transfer_crud.links_of([root.code])).get(root.code)
    children = await transfer_crud.live_children(root.code) if root_link is None or root_link.parent_code is None else []
    tasks = [root, *children]
    task_codes = [task.code for task in tasks]
    child_links = await transfer_crud.links_of(task.code for task in children)
    stages = await transfer_crud.stages_of(task_codes)
    journal = await transfer_crud.journal_of(task_codes)
    notes = await transfer_crud.live_notes_of(task_codes)
    live_note_codes = {note.code for _, note in notes}
    files = [view for task_code in task_codes for view in await task_file_views(task_code)]

    texts: list[str | None] = []
    with ArchiveWriter(path, TASK_ARCHIVE) as archive:
        task_rows = []
        for task in tasks:
            task_rows.append(row_to_json(task, omit=_TASK_OMITTED))
            texts += [getattr(task, field) for field in TASK_TEXTS]
        archive.add_rows(rows_entry(ENTITY_TASKS), task_rows)
        archive.add_rows(
            rows_entry(ENTITY_LINKS),
            [row_to_json(child_links[task.code]) for task in children if task.code in child_links],
        )

        archive.add_rows(rows_entry(ENTITY_STAGES), [row_to_json(stage) for stage in stages])
        texts += [getattr(stage, field) for stage in stages for field in STAGE_TEXTS]

        archive.add_rows(rows_entry(ENTITY_JOURNAL), [row_to_json(entry) for entry in journal])
        texts += [getattr(entry, field) for entry in journal for field in JOURNAL_TEXTS]

        archive.add_rows(
            rows_entry(ENTITY_NOTES),
            [{"link": row_to_json(link), "note": row_to_json(note, omit=("body", "deleted_at"))} for link, note in notes],
        )
        for _, note in notes:
            archive.add_text(note_body_entry(note.code), note.body)
            texts += [getattr(note, field) for field in NOTE_TEXTS] + [note.body]

        file_rows: list[dict[str, Any]] = []
        written: set[str] = set()
        for view in files:
            binding = row_to_json(view.binding)
            if binding["note_code"] is not None and binding["note_code"] not in live_note_codes:
                binding["note_code"] = None
            entry = file_entry(view.stored.code, view.stored.extension)
            file_rows.append({
                "binding": binding,
                "stored": {
                    "sha256": view.stored.sha256,
                    "size": view.stored.size,
                    "mime": view.stored.mime,
                    "type": view.stored.type,
                    "extension": view.stored.extension,
                    "created_at": datetime_to_agent(view.stored.created_at),
                },
                "name": f"{view.original_filename}{view.original_extension}",
                "entry": entry,
            })
            texts += [getattr(view.binding, field) for field in FILE_TEXTS]
            # One content is one file: a subtask holding the root's file shares its bytes.
            if entry not in written:
                archive.add_file(entry, file_path(view.stored))
                written.add(entry)
        archive.add_rows(rows_entry(ENTITY_FILES), file_rows)

        workspace = await workspace_get(root.workspace_code, include_deleted=True)
        manifest = archive.finish(
            archive_id=str(ULID()),
            source=ManifestSource(
                install_id=await install_id(),
                app_version=app_version(),
                extra={
                    "workspace_code": root.workspace_code,
                    "workspace_title": workspace.title if workspace is not None else "",
                },
            ),
            root=ManifestRoot(code=root.code, title=root.title),
            counts={
                ENTITY_TASKS: len(tasks),
                ENTITY_STAGES: len(stages),
                ENTITY_JOURNAL: len(journal),
                ENTITY_NOTES: len(notes),
                ENTITY_FILES: len(file_rows),
            },
            dangling_refs=_dangling(
                texts,
                {
                    TASK_CODE_PREFIX: set(task_codes),
                    STAGE_CODE_PREFIX: {stage.code for stage in stages},
                    JOURNAL_CODE_PREFIX: {entry.code for entry in journal},
                    NOTE_CODE_PREFIX: live_note_codes,
                    FILE_CODE_PREFIX: {view.stored.code for view in files},
                },
            ),
        )

    return ExportedArchive(
        path=path,
        file_name=archive_file_name(root.title, fallback=f"task-{root.code}", extension=TASK_ARCHIVE.extension),
        manifest=manifest,
    )


def _dangling(texts: list[str | None], present: dict[str, set[str]]) -> list[str]:
    mentioned: set[tuple[str, str]] = set()
    for text in texts:
        mentioned |= OUTSIDE_REFERENCES.collect(text)
    return sorted(
        f"{word}@{code}" for word, code in mentioned if code not in present.get(word, set())
    )


__all__ = ["ExportedArchive", "export_task"]
