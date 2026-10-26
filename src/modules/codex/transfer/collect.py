"""Export of a codex into a ``.ucdx`` archive — the whole of it, reading only.

What goes: the codex with its rules, every record of every level with its code, segment, parent
and place — the deleted ones too, with their marks, so the bin travels with the tree — and every
file a record holds, the bytes too. What does not: the mounts (one installation's layout), a file
the file manager deleted.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ulid import ULID

from src.core.utils.date import datetime_to_agent
from src.core.version import app_version
from src.modules.codex.constants import CODEX_CODE_PREFIX, FILE_CODE_PREFIX
from src.modules.codex.crud import codex as codex_crud
from src.modules.codex.crud import transfer as transfer_crud
from src.modules.codex.files import codex_file_views
from src.modules.codex.transfer.constants import (
    CODEX_ARCHIVE,
    CODEX_TEXTS,
    ENTITY_CODEX,
    ENTITY_FILES,
    ENTITY_NOTES,
    FILE_TEXTS,
    NOTE_TEXTS,
    OUTSIDE_REFERENCES,
    codex_body_entry,
    file_entry,
    note_body_entry,
    rows_entry,
)
from src.modules.core_storage.services.files import file_path
from src.modules.core_transfer.container import ArchiveWriter
from src.modules.core_transfer.install import install_id
from src.modules.core_transfer.manifest import Manifest, ManifestRoot, ManifestSource
from src.modules.core_transfer.naming import archive_file_name
from src.modules.core_transfer.rows import row_to_json


@dataclass(frozen=True)
class ExportedArchive:
    path: Path
    file_name: str
    manifest: Manifest


async def export_codex(code: str, path: Path) -> ExportedArchive:
    """Write the archive of a codex, a deleted one too; ``LookupError`` — no such codex."""
    codex = await codex_crud.codex_get(code, include_deleted=True)
    if codex is None:
        raise LookupError(code)
    notes = await transfer_crud.notes_of(codex.code)
    files = [view for note in notes for view in await codex_file_views(note.code)]

    texts: list[str | None] = [getattr(codex, field) for field in CODEX_TEXTS] + [codex.body]
    with ArchiveWriter(path, CODEX_ARCHIVE) as archive:
        archive.add_rows(rows_entry(ENTITY_CODEX), [row_to_json(codex, omit=("body",))])
        archive.add_text(codex_body_entry(codex.code), codex.body)

        archive.add_rows(rows_entry(ENTITY_NOTES), [row_to_json(note, omit=("body",)) for note in notes])
        for note in notes:
            archive.add_text(note_body_entry(note.code), note.body)
            texts += [getattr(note, field) for field in NOTE_TEXTS] + [note.body]

        file_rows: list[dict[str, Any]] = []
        written: set[str] = set()
        for view in files:
            entry = file_entry(view.stored.code, view.stored.extension)
            file_rows.append({
                "binding": row_to_json(view.binding),
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
            if entry not in written:
                archive.add_file(entry, file_path(view.stored))
                written.add(entry)
        archive.add_rows(rows_entry(ENTITY_FILES), file_rows)

        present = {
            CODEX_CODE_PREFIX: {codex.code, *(note.code for note in notes)},
            FILE_CODE_PREFIX: {view.stored.code for view in files},
        }
        mentioned: set[tuple[str, str]] = set()
        for text in texts:
            mentioned |= OUTSIDE_REFERENCES.collect(text)
        manifest = archive.finish(
            archive_id=str(ULID()),
            source=ManifestSource(install_id=await install_id(), app_version=app_version()),
            root=ManifestRoot(code=codex.code, title=codex.title, extra={"segment": codex.segment}),
            counts={
                ENTITY_NOTES: len(notes),
                "deleted_notes": sum(1 for note in notes if note.deleted_at is not None),
                ENTITY_FILES: len(file_rows),
            },
            dangling_refs=sorted(
                f"{word}@{code}" for word, code in mentioned if code not in present.get(word, set())
            ),
        )

    return ExportedArchive(
        path=path,
        file_name=archive_file_name(codex.title, fallback=f"codex-{codex.segment}", extension=CODEX_ARCHIVE.extension),
        manifest=manifest,
    )


__all__ = ["ExportedArchive", "export_codex"]
