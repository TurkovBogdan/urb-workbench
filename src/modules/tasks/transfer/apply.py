"""Applying a task import: the codes decided, the files taken, then every row in one transaction.

The order is fixed by the storage: taking a file opens a write transaction of the storage's own,
and on SQLite a writer nested in ours would wait for the lock until the timeout. So:

1. every final code is decided — kept, or a new one where the person chose «replace» or another
   task holds it;
2. under the files lock of every target task, each file is taken for its tasks — stored under its
   code, or attached where the same content already is; the owners this import added are noted;
3. one ``write_scope`` writes the tasks, the tree, the stages, the journal, the notes and the
   bindings, with every reference in their texts moved to the final codes. ORM objects, not bulk
   statements: the change feed takes its events from the session;
4. a failure in 3 gives back the owners of 2 — the rows are rolled back, a file left with no owner
   goes to the storage's cleanup by its term.

«Update» merges, it does not mirror: what the task here has and the archive does not — a stage,
an entry, a note, a file, a subtask — stays.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import select

from src.core.database import write_scope
from src.core.utils.date import utc_now
from src.modules.core_storage.dto import Owner
from src.modules.core_storage.services.ownership import file_owners
from src.modules.core_transfer.constants import CHOICE_UPDATE
from src.modules.core_transfer.container import ArchiveReader
from src.modules.core_transfer.files import FILE_RECODE, FILE_REUSE, FileVerdict, release_taken, take_file
from src.modules.core_transfer.rows import clip_to_columns, json_to_values, moment
from src.modules.notes.constants import BODY_MAX as NOTE_BODY_MAX
from src.modules.notes.constants import DESCRIPTION_MAX as NOTE_DESCRIPTION_MAX
from src.modules.notes.constants import TITLE_MAX as NOTE_TITLE_MAX
from src.modules.notes.crud.note import note_put
from src.modules.notes.models.note import Note
from src.modules.tasks.codes import new_code
from src.modules.tasks.constants import (
    FILE_CODE_PREFIX,
    FILE_STORE,
    JOURNAL_CODE_PREFIX,
    NOTE_CODE_PREFIX,
    STAGE_CODE_PREFIX,
    TASK_CODE_PREFIX,
)
from src.modules.tasks.crud import transfer as transfer_crud
from src.modules.tasks.crud.link import bottom_sort
from src.modules.tasks.crud.task import _carry_children
from src.modules.tasks.file_owner import task_owner, tasks_files_lock
from src.modules.tasks.models.file import TasksFile
from src.modules.tasks.models.journal import TasksJournal
from src.modules.tasks.models.link import TasksLink
from src.modules.tasks.models.note import TasksNote
from src.modules.tasks.models.stage import TasksStage
from src.modules.tasks.models.task import TasksTask
from src.modules.tasks.transfer.constants import (
    FILE_TEXTS,
    JOURNAL_TEXTS,
    NOTE_TEXTS,
    REFERENCES,
    STAGE_TEXTS,
    TASK_TEXTS,
    note_body_entry,
)
from src.modules.tasks.transfer.plan import ImportPlan

_ENTITIES = ("tasks", "stages", "journal", "notes", "files")


@dataclass
class ImportReport:
    """What the import did — what the plan promised, as fact."""

    task_code: str
    title: str
    created: dict[str, int] = field(default_factory=lambda: dict.fromkeys(_ENTITIES, 0))
    updated: dict[str, int] = field(default_factory=lambda: dict.fromkeys(_ENTITIES, 0))
    recoded: list[dict[str, str]] = field(default_factory=list)
    renumbered: list[dict[str, Any]] = field(default_factory=list)
    truncated: list[dict[str, str]] = field(default_factory=list)
    refs_rewritten: int = 0

    def body(self, dangling: list[str]) -> dict[str, Any]:
        return {
            "task": {"code": f"{TASK_CODE_PREFIX}@{self.task_code}", "title": self.title},
            "counts": {"created": self.created, "updated": self.updated},
            "recoded": self.recoded,
            "renumbered": self.renumbered,
            "truncated": self.truncated,
            "refs_rewritten": self.refs_rewritten,
            "dangling_refs": dangling,
        }


class _Codes:
    """Fresh codes, free in their table and among the ones handed out by this import."""

    def __init__(self) -> None:
        self._reserved: set[str] = set()

    def reserve(self, codes: Iterable[str]) -> None:
        self._reserved |= set(codes)

    async def fresh(self, model: Any) -> str:
        while True:
            code = new_code()
            if code in self._reserved or await transfer_crud.codes_in_use(model, [code]):
                continue
            self._reserved.add(code)
            return code


async def apply_plan(
    reader: ArchiveReader, plan: ImportPlan, choices: dict[str, str], *, group_code: str | None
) -> ImportReport:
    content = plan.content
    codes = _Codes()
    codes.reserve(row["code"] for row in content.tasks)
    codes.reserve(row["code"] for row in content.stages)
    codes.reserve(row["code"] for row in content.journal)
    codes.reserve(row["note"]["code"] for row in content.notes)

    def updates(prefix: str, code: str) -> bool:
        return choices.get(f"{prefix}@{code}") == CHOICE_UPDATE

    task_code: dict[str, str] = {}
    for row in content.tasks:
        code = row["code"]
        keeps = code not in plan.local_tasks or updates(TASK_CODE_PREFIX, code)
        task_code[code] = code if keeps else await codes.fresh(TasksTask)

    note_code: dict[str, str] = {}
    for row in content.notes:
        code = row["note"]["code"]
        keeps = code not in plan.local_notes or updates(NOTE_CODE_PREFIX, code)
        note_code[code] = code if keeps else await codes.fresh(Note)

    async def follower(code: str, owner: str, local: dict[str, Any], model: Any) -> str:
        """A stage's or an entry's code: kept unless another task holds it."""
        held = local.get(code)
        if held is None or (held.task_code == owner and task_code[owner] == owner):
            return code
        return await codes.fresh(model)

    stage_code = {row["code"]: await follower(row["code"], row["task_code"], plan.local_stages, TasksStage)
                  for row in content.stages}
    entry_code = {row["code"]: await follower(row["code"], row["task_code"], plan.local_journal, TasksJournal)
                  for row in content.journal}

    root = content.root
    report = ImportReport(task_code=task_code[root["code"]], title=root["title"])
    final_tasks = sorted(set(task_code.values()))

    async with tasks_files_lock(final_tasks):
        file_code, taken = await _take_files(reader, plan, task_code)
        try:
            refs = _reference_map(task_code, stage_code, entry_code, note_code, file_code)
            async with write_scope() as s:
                await _write_rows(s, plan, report, refs, reader, group_code=group_code, task_code=task_code,
                                  stage_code=stage_code, entry_code=entry_code, note_code=note_code,
                                  file_code=file_code)
        except BaseException:
            await release_taken(taken)
            raise

    report.recoded = _recoded(plan, task_code, stage_code, entry_code, note_code, file_code)
    return report


async def _take_files(
    reader: ArchiveReader, plan: ImportPlan, task_code: dict[str, str]
) -> tuple[dict[str, str], list[tuple[str, Owner]]]:
    """``archive code → code here`` of every file, and the owners this import added."""
    holders: dict[str, list[str]] = {}
    for row in plan.content.files:
        binding = row["binding"]
        holders.setdefault(binding["file_code"], []).append(task_code[binding["task_code"]])

    file_code: dict[str, str] = {}
    taken: list[tuple[str, Owner]] = []
    try:
        for code, tasks in holders.items():
            verdict = plan.verdicts[code]
            for target in tasks:
                owner = task_owner(target)
                # Only a file stored here already may have this owner: a re-import of the same task.
                known = verdict.local.code if verdict.outcome in (FILE_REUSE, FILE_RECODE) and verdict.local else None
                had = known is not None and owner in {o.owner for o in await file_owners(known)}
                stored = await take_file(reader, verdict, owner=owner, store=FILE_STORE)
                if not had:
                    taken.append((stored.code, owner))
                file_code[code] = stored.code
                # Every next holder of the same file attaches to what is stored now.
                verdict = FileVerdict(verdict.archived, FILE_REUSE, stored)
    except BaseException:
        await release_taken(taken)
        raise
    return file_code, taken


def _reference_map(task_code, stage_code, entry_code, note_code, file_code) -> dict[tuple[str, str], str]:
    refs: dict[tuple[str, str], str] = {}
    for prefix, mapping in (
        (TASK_CODE_PREFIX, task_code),
        (STAGE_CODE_PREFIX, stage_code),
        (JOURNAL_CODE_PREFIX, entry_code),
        (NOTE_CODE_PREFIX, note_code),
        (FILE_CODE_PREFIX, file_code),
    ):
        refs.update({(prefix, old): new for old, new in mapping.items()})
    return refs


def _rewrite(values: dict[str, Any], fields: Iterable[str], refs, report: ImportReport) -> None:
    for name in fields:
        text, count = REFERENCES.rewrite(values.get(name), refs)
        values[name] = text if text is not None else ""
        report.refs_rewritten += count


def _clip(model: Any, values: dict[str, Any], entity: str, code: str, report: ImportReport) -> dict[str, Any]:
    values, clipped = clip_to_columns(model, values)
    report.truncated += [{"entity": entity, "code": code, "field": name} for name in clipped]
    return values


def _assign(row: Any, values: dict[str, Any], *, keep: Iterable[str] = ()) -> None:
    for name, value in values.items():
        if name not in keep:
            setattr(row, name, value)


async def _write_rows(s, plan: ImportPlan, report: ImportReport, refs, reader: ArchiveReader, *,
                      group_code, task_code, stage_code, entry_code, note_code, file_code) -> None:
    content = plan.content
    workspace = plan.workspace_code
    now = utc_now()
    root = content.root["code"]
    root_final = task_code[root]

    # ── tasks ──────────────────────────────────────────────────────────────
    previous_group: str | None = None
    for row in content.tasks:
        final = task_code[row["code"]]
        values = json_to_values(TasksTask, row, omit=("workspace_code", "group_code"))
        values.update(code=final, workspace_code=workspace, group_code=group_code, updated_at=now, deleted_at=None)
        _rewrite(values, TASK_TEXTS, refs, report)
        values = _clip(TasksTask, values, "task", f"{TASK_CODE_PREFIX}@{final}", report)
        existing = await s.get(TasksTask, final)
        if existing is None:
            s.add(TasksTask(**values))
            report.created["tasks"] += 1
        else:
            if final == root_final:
                previous_group = existing.group_code
            _assign(existing, values, keep=("code",))
            report.updated["tasks"] += 1
    await s.flush()

    # ── tree ───────────────────────────────────────────────────────────────
    root_link = await s.get(TasksLink, root_final)
    keeps_place = root_link is not None and root_link.parent_code is None and previous_group == group_code
    if root_link is None:
        s.add(TasksLink(task_code=root_final, parent_code=None,
                        sort=await bottom_sort(s, None, workspace, group_code, moved_code=root_final)))
    elif not keeps_place:
        root_link.parent_code = None
        root_link.sort = await bottom_sort(s, None, workspace, group_code, moved_code=root_final)
    for child, row in content.links.items():
        final = task_code[child]
        link = await s.get(TasksLink, final)
        if link is None:
            s.add(TasksLink(task_code=final, parent_code=root_final, sort=row["sort"]))
        else:
            link.parent_code = root_final
            link.sort = row["sort"]
    await s.flush()
    # A subtask lives in its parent's group: the ones here the archive does not know follow the
    # updated root into the group it was imported to.
    await _carry_children(s, await s.get(TasksTask, root_final))
    await s.flush()

    # ── stages ─────────────────────────────────────────────────────────────
    finals = sorted(set(task_code.values()))
    local_stages = (await s.execute(select(TasksStage).where(TasksStage.task_code.in_(finals)))).scalars().all()
    archived = {stage_code[row["code"]] for row in content.stages}
    taken_numbers: dict[str, set[int]] = {}
    for parked, stage in enumerate(local_stages, start=1):
        if stage.code in archived:
            # Out of the way first: two updated stages swapping their numbers would hit the
            # unique index in the middle of the swap.
            stage.number = -parked
        else:
            taken_numbers.setdefault(stage.task_code, set()).add(stage.number)
    await s.flush()
    for row in sorted(content.stages, key=lambda r: (r["task_code"], r["number"])):
        final, owner = stage_code[row["code"]], task_code[row["task_code"]]
        numbers = taken_numbers.setdefault(owner, set())
        number = row["number"]
        if number in numbers:
            number = max(numbers) + 1
            report.renumbered.append({"code": f"{STAGE_CODE_PREFIX}@{final}", "title": row["title"],
                                      "from": row["number"], "to": number})
        numbers.add(number)
        values = json_to_values(TasksStage, row)
        values.update(code=final, task_code=owner, number=number, updated_at=now)
        _rewrite(values, STAGE_TEXTS, refs, report)
        values = _clip(TasksStage, values, "stage", f"{STAGE_CODE_PREFIX}@{final}", report)
        existing = await s.get(TasksStage, final)
        if existing is None:
            s.add(TasksStage(**values))
            report.created["stages"] += 1
        else:
            _assign(existing, values, keep=("code",))
            report.updated["stages"] += 1
    await s.flush()

    # ── journal ────────────────────────────────────────────────────────────
    for row in content.journal:
        final = entry_code[row["code"]]
        values = json_to_values(TasksJournal, row)
        values.update(code=final, task_code=task_code[row["task_code"]],
                      stage_code=stage_code.get(row["stage_code"]) if row.get("stage_code") else None)
        _rewrite(values, JOURNAL_TEXTS, refs, report)
        values = _clip(TasksJournal, values, "journal", f"{JOURNAL_CODE_PREFIX}@{final}", report)
        existing = await s.get(TasksJournal, final)
        if existing is None:
            s.add(TasksJournal(**values))
            report.created["journal"] += 1
        else:
            _assign(existing, values, keep=("code",))
            report.updated["journal"] += 1
    await s.flush()

    # ── notes ──────────────────────────────────────────────────────────────
    for row in content.notes:
        archived_code = row["note"]["code"]
        final = note_code[archived_code]
        owner = task_code[row["link"]["task_code"]]
        values = {
            "title": row["note"].get("title") or "",
            "description": row["note"].get("description") or "",
            # One body at a time: the plan bounded each, nothing bounds their sum.
            "body": reader.text(note_body_entry(archived_code)),
        }
        _rewrite(values, (*NOTE_TEXTS, "body"), refs, report)
        for name, limit in (("title", NOTE_TITLE_MAX), ("description", NOTE_DESCRIPTION_MAX), ("body", NOTE_BODY_MAX)):
            if len(values[name]) > limit:
                values[name] = values[name][:limit]
                report.truncated.append({"entity": "note", "code": f"{NOTE_CODE_PREFIX}@{final}", "field": name})
        existed = await s.get(Note, final) is not None
        await note_put(final, title=values["title"], description=values["description"], body=values["body"],
                       created_at=moment(row["note"].get("created_at")), session=s)
        link = await s.get(TasksNote, final)
        sort = row["link"]["sort"]
        if link is None:
            s.add(TasksNote(note_code=final, task_code=owner, sort=sort,
                            created_at=moment(row["link"].get("created_at")) or now))
        else:
            link.task_code = owner
            link.sort = sort
        if existed:
            report.updated["notes"] += 1
        else:
            report.created["notes"] += 1
    await s.flush()

    # ── file bindings ──────────────────────────────────────────────────────
    for row in content.files:
        binding = row["binding"]
        owner = task_code[binding["task_code"]]
        final = file_code[binding["file_code"]]
        values = json_to_values(TasksFile, binding)
        values.update(
            task_code=owner,
            file_code=final,
            note_code=note_code.get(binding["note_code"]) if binding.get("note_code") else None,
            stage_code=stage_code.get(binding["stage_code"]) if binding.get("stage_code") else None,
            updated_at=now,
        )
        _rewrite(values, FILE_TEXTS, refs, report)
        values = _clip(TasksFile, values, "file", f"{FILE_CODE_PREFIX}@{final}", report)
        existing = await s.get(TasksFile, (owner, final))
        if existing is None:
            s.add(TasksFile(**values))
            report.created["files"] += 1
        else:
            _assign(existing, values, keep=("task_code", "file_code"))
            report.updated["files"] += 1
    await s.flush()


def _recoded(plan: ImportPlan, task_code, stage_code, entry_code, note_code, file_code) -> list[dict[str, str]]:
    content = plan.content
    found: list[dict[str, str]] = []
    for entity, prefix, mapping, titles in (
        ("task", TASK_CODE_PREFIX, task_code, {row["code"]: row["title"] for row in content.tasks}),
        ("stage", STAGE_CODE_PREFIX, stage_code, {row["code"]: row["title"] for row in content.stages}),
        ("journal", JOURNAL_CODE_PREFIX, entry_code, {row["code"]: row["title"] for row in content.journal}),
        ("note", NOTE_CODE_PREFIX, note_code, {row["note"]["code"]: row["note"]["title"] for row in content.notes}),
        ("file", FILE_CODE_PREFIX, file_code,
         {row["binding"]["file_code"]: row["binding"].get("title") or row.get("name") or "" for row in content.files}),
    ):
        for old, new in mapping.items():
            if old != new:
                found.append({"entity": entity, "title": titles.get(old, ""), "from": f"{prefix}@{old}", "to": f"{prefix}@{new}"})
    return found


__all__ = ["ImportReport", "apply_plan"]
