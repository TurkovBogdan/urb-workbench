"""Helpers of the task transfer tests: an import in two phases, and a snapshot of what a task is."""

from __future__ import annotations

import hashlib
import json
import zipfile
from pathlib import Path
from typing import Any

from src.modules.core_storage.services.files import file_get_many
from src.modules.core_transfer.rows import row_to_json
from src.modules.tasks.crud import transfer as transfer_crud
from src.modules.tasks.models.task import TasksTask
from src.modules.tasks.transfer.runner import analyze_archive, import_archive

VOLATILE = ("updated_at",)


def rewrite_archive(source: Path, target: Path, replace: dict[str, bytes]) -> Path:
    """A copy of an archive with entries replaced and the manifest's inventory made to match —
    what a crafted archive looks like: whole by its sums, lying in its rows."""
    with zipfile.ZipFile(source) as old:
        manifest = json.loads(old.read("manifest.json"))
        for item in manifest["files"]:
            if item["path"] in replace:
                item["bytes"] = len(replace[item["path"]])
                item["sha256"] = hashlib.sha256(replace[item["path"]]).hexdigest()
        with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as new:
            for info in old.infolist():
                if info.filename == "manifest.json":
                    data = json.dumps(manifest).encode()
                else:
                    data = replace.get(info.filename, old.read(info.filename))
                new.writestr(zipfile.ZipInfo(info.filename), data, compress_type=info.compress_type)
    return target


def jsonl(rows: list[dict]) -> bytes:
    return "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows).encode()


def read_rows(path: Path, entry: str) -> list[dict]:
    with zipfile.ZipFile(path) as archive:
        return [json.loads(line) for line in archive.read(entry).decode().split("\n") if line]


async def run_import(path: Path, workspace: str, *, group: str | None = None,
                     decisions: dict[str, str] | None = None):
    plan = await analyze_archive(path, workspace_code=workspace)
    _, report = await import_archive(
        path, workspace_code=workspace, group_code=group, decisions=decisions or {}, plan_token=plan.token,
    )
    return plan, report


async def snapshot(task_codes: list[str]) -> dict[str, Any]:
    """Every row of the tasks as the archive would carry it, without what an import may change."""
    tasks = await transfer_crud.rows_by_codes(TasksTask, task_codes)
    stages = await transfer_crud.stages_of(task_codes)
    journal = await transfer_crud.journal_of(task_codes)
    notes = await transfer_crud.live_notes_of(task_codes)
    bindings = await transfer_crud.bindings_of(task_codes)
    stored = await file_get_many([code for _, code in bindings])
    return {
        "tasks": {code: row_to_json(row, omit=("workspace_code", "group_code", *VOLATILE)) for code, row in tasks.items()},
        "stages": {row.code: row_to_json(row, omit=VOLATILE) for row in stages},
        "journal": {row.code: row_to_json(row) for row in journal},
        "notes": {
            note.code: {**row_to_json(note, omit=VOLATILE), "task_code": link.task_code, "sort": link.sort}
            for link, note in notes
        },
        "files": {
            key: {**row_to_json(row, omit=VOLATILE), "sha256": stored[key[1]].sha256}
            for key, row in bindings.items()
        },
    }
