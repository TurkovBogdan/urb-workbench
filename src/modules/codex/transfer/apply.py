"""Applying a codex import: the codes decided, the files taken, then the tree in one transaction.

Same order as a task import, for the same reason (the storage's own transaction cannot nest in
ours): the final codes; the files under the files lock of every target record; then one
``write_scope`` — under the tree's advisory lock on PostgreSQL, like every structural change —
writes the codex, the records parents first, the bindings and the mount. A failure there gives
the owners back.

Segments are resolved as the rows land: a live record takes its archive segment unless a live
sibling here holds it, then the first free ``-2``, ``-3``…; the records the archive updates are
parked first so their old segments do not block the new layout. After the writes the four levels
are checked once more over the whole codex: the plan made sure of it, this is the net.

«Update» merges: records and files the codex here has and the archive does not stay.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import func, select

from src.core.database import write_scope
from src.core.utils.date import utc_now
from src.modules.codex.codes import new_code
from src.modules.codex.constants import CODEX_CODE_PREFIX, FILE_CODE_PREFIX, FILE_STORE, SEGMENT_MAX, SORT_DEFAULT, SORT_STEP
from src.modules.codex.crud import transfer as transfer_crud
from src.modules.codex.crud.note import _lock_tree
from src.modules.codex.file_owner import note_owner
from src.modules.codex.models import Codex, CodexFile, CodexMount, CodexNote
from src.modules.codex.rules import DEPTH_MAX
from src.modules.codex.transfer.constants import (
    CODEX_TEXTS,
    FILE_TEXTS,
    NOTE_TEXTS,
    REFERENCES,
    codex_body_entry,
    note_body_entry,
)
from src.modules.codex.transfer.plan import ImportPlan
from src.modules.core_storage.dto import Owner
from src.modules.core_storage.services.holder_lock import holder_locks
from src.modules.core_storage.services.ownership import file_owners
from src.modules.core_transfer.constants import CHOICE_UPDATE
from src.modules.core_transfer.container import ArchiveReader
from src.modules.core_transfer.errors import DEPTH_EXCEEDED, TransferError
from src.modules.core_transfer.files import FILE_RECODE, FILE_REUSE, FileVerdict, release_taken, take_file
from src.modules.core_transfer.rows import clip_to_columns, json_to_values

_ENTITIES = ("codex", "notes", "files")


@dataclass
class ImportReport:
    codex_code: str
    title: str
    segment: str = ""
    mounted: bool = False
    created: dict[str, int] = field(default_factory=lambda: dict.fromkeys(_ENTITIES, 0))
    updated: dict[str, int] = field(default_factory=lambda: dict.fromkeys(_ENTITIES, 0))
    recoded: list[dict[str, str]] = field(default_factory=list)
    repathed: list[dict[str, str]] = field(default_factory=list)
    # Records here the archive does not know that went to the bin with a parent the archive binned.
    binned: list[dict[str, str]] = field(default_factory=list)
    truncated: list[dict[str, str]] = field(default_factory=list)
    refs_rewritten: int = 0

    def body(self, dangling: list[str]) -> dict[str, Any]:
        return {
            "codex": {"code": f"{CODEX_CODE_PREFIX}@{self.codex_code}", "title": self.title, "segment": self.segment},
            "mounted": self.mounted,
            "counts": {"created": self.created, "updated": self.updated},
            "recoded": self.recoded,
            "repathed": self.repathed,
            "binned": self.binned,
            "truncated": self.truncated,
            "refs_rewritten": self.refs_rewritten,
            "dangling_refs": dangling,
        }


def free_segment(wanted: str, taken: set[str]) -> str:
    """The segment itself, or the first ``<segment>-N`` free among ``taken``, within the width."""
    if wanted not in taken:
        return wanted
    number = 2
    while True:
        suffix = f"-{number}"
        candidate = f"{wanted[: SEGMENT_MAX - len(suffix)]}{suffix}"
        if candidate not in taken:
            return candidate
        number += 1


async def apply_plan(
    reader: ArchiveReader, plan: ImportPlan, choices: dict[str, str], *, workspace_code: str | None
) -> ImportReport:
    content = plan.content
    root = content.codex["code"]
    reserved = {root, *(row["code"] for row in content.notes)}

    async def fresh() -> str:
        while True:
            code = new_code()
            codexes, notes = await transfer_crud.code_holders([code])
            if code not in reserved and not codexes and not notes:
                reserved.add(code)
                return code

    def taken(code: str) -> bool:
        return code in plan.local_codexes or code in plan.local_notes

    def updates(code: str) -> bool:
        return choices.get(f"{CODEX_CODE_PREFIX}@{code}") == CHOICE_UPDATE

    codex_final = root if not taken(root) or updates(root) else await fresh()
    note_final = {}
    for row in content.notes:
        code = row["code"]
        note_final[code] = code if not taken(code) or updates(code) else await fresh()

    report = ImportReport(codex_code=codex_final, title=content.codex["title"])
    rules = reader.text(codex_body_entry(root))

    async with holder_locks(CODEX_CODE_PREFIX, sorted(note_final.values())):
        file_code, owners_taken = await _take_files(reader, plan, note_final)
        try:
            refs = {(CODEX_CODE_PREFIX, root): codex_final}
            refs.update({(CODEX_CODE_PREFIX, old): new for old, new in note_final.items()})
            refs.update({(FILE_CODE_PREFIX, old): new for old, new in file_code.items()})
            async with write_scope() as s:
                await _lock_tree(s)
                await _write(s, plan, report, refs, rules, reader, codex_final=codex_final,
                             note_final=note_final, file_code=file_code, workspace_code=workspace_code)
        except BaseException:
            await release_taken(owners_taken)
            raise

    report.recoded = _recoded(plan, codex_final, note_final, file_code)
    return report


async def _take_files(reader, plan: ImportPlan, note_final: dict[str, str]):
    holders: dict[str, list[str]] = {}
    for row in plan.content.files:
        holders.setdefault(row["binding"]["file_code"], []).append(note_final[row["binding"]["note_code"]])
    file_code: dict[str, str] = {}
    taken: list[tuple[str, Owner]] = []
    try:
        for code, notes in holders.items():
            verdict = plan.verdicts[code]
            for note in notes:
                owner = note_owner(note)
                known = verdict.local.code if verdict.outcome in (FILE_REUSE, FILE_RECODE) and verdict.local else None
                had = known is not None and owner in {o.owner for o in await file_owners(known)}
                stored = await take_file(reader, verdict, owner=owner, store=FILE_STORE)
                if not had:
                    taken.append((stored.code, owner))
                file_code[code] = stored.code
                verdict = FileVerdict(verdict.archived, FILE_REUSE, stored)
    except BaseException:
        await release_taken(taken)
        raise
    return file_code, taken


def _rewrite(values: dict[str, Any], fields: Iterable[str], refs, report: ImportReport) -> None:
    for name in fields:
        text, count = REFERENCES.rewrite(values.get(name), refs)
        values[name] = text if text is not None else ""
        report.refs_rewritten += count


def _clip(model, values, entity: str, code: str, report: ImportReport) -> dict[str, Any]:
    values, clipped = clip_to_columns(model, values)
    report.truncated += [{"entity": entity, "code": code, "field": name} for name in clipped]
    return values


async def _write(s, plan: ImportPlan, report: ImportReport, refs, rules: str, reader: ArchiveReader, *,
                 codex_final: str, note_final: dict[str, str], file_code: dict[str, str],
                 workspace_code: str | None) -> None:
    content = plan.content
    now = utc_now()

    # ── the codex ──────────────────────────────────────────────────────────
    values = json_to_values(Codex, content.codex, omit=("body",))
    values.update(code=codex_final, body=rules, updated_at=now)
    _rewrite(values, (*CODEX_TEXTS, "body"), refs, report)
    if values.get("deleted_at") is None:
        holders = (await s.execute(
            select(Codex.segment).where(Codex.deleted_at.is_(None), Codex.code != codex_final)
        )).scalars().all()
        segment = free_segment(values["segment"], set(holders))
        if segment != values["segment"]:
            report.repathed.append({"entity": "codex", "title": values["title"],
                                    "from": f"/{values['segment']}", "to": f"/{segment}"})
            values["segment"] = segment
    values = _clip(Codex, values, "codex", f"{CODEX_CODE_PREFIX}@{codex_final}", report)
    existing = await s.get(Codex, codex_final)
    if existing is None:
        s.add(Codex(**values))
        report.created["codex"] = 1
    else:
        for name, value in values.items():
            if name != "code":
                setattr(existing, name, value)
        report.updated["codex"] = 1
    report.segment = values["segment"]
    await s.flush()

    # ── records: the updated ones parked, then parents first ───────────────
    updated = [await s.get(CodexNote, final) for final in note_final.values()]
    for row in updated:
        if row is not None:
            row.segment = f"~{row.code.lower()}"
    await s.flush()

    for row in content.notes:
        final = note_final[row["code"]]
        parent = note_final.get(row["parent_code"]) if row.get("parent_code") else None
        values = json_to_values(CodexNote, row, omit=("body",))
        # One body at a time: the plan bounded each, nothing bounds their sum.
        values.update(code=final, codex_code=codex_final, parent_code=parent,
                      body=reader.text(note_body_entry(row["code"])), updated_at=now)
        _rewrite(values, (*NOTE_TEXTS, "body"), refs, report)
        if values.get("deleted_at") is None:
            siblings = select(CodexNote.segment).where(
                CodexNote.codex_code == codex_final,
                CodexNote.deleted_at.is_(None),
                CodexNote.code != final,
                CodexNote.parent_code.is_(None) if parent is None else CodexNote.parent_code == parent,
            )
            segment = free_segment(values["segment"], set((await s.execute(siblings)).scalars().all()))
            if segment != values["segment"]:
                report.repathed.append({"entity": "record", "title": values["title"],
                                        "from": values["segment"], "to": segment,
                                        "code": f"{CODEX_CODE_PREFIX}@{final}"})
                values["segment"] = segment
        values = _clip(CodexNote, values, "record", f"{CODEX_CODE_PREFIX}@{final}", report)
        existing = await s.get(CodexNote, final)
        if existing is None:
            s.add(CodexNote(**values))
            report.created["notes"] += 1
        else:
            for name, value in values.items():
                if name != "code":
                    setattr(existing, name, value)
            report.updated["notes"] += 1
        await s.flush()

    await _bin_orphans(s, plan, report, codex_final=codex_final, note_final=note_final)

    # ── bindings ───────────────────────────────────────────────────────────
    for row in content.files:
        binding = row["binding"]
        note, final_file = note_final[binding["note_code"]], file_code[binding["file_code"]]
        values = json_to_values(CodexFile, binding)
        values.update(note_code=note, file_code=final_file, updated_at=now)
        _rewrite(values, FILE_TEXTS, refs, report)
        values = _clip(CodexFile, values, "file", f"{FILE_CODE_PREFIX}@{final_file}", report)
        existing = await s.get(CodexFile, (note, final_file))
        if existing is None:
            s.add(CodexFile(**values))
            report.created["files"] += 1
        else:
            for name, value in values.items():
                if name not in ("note_code", "file_code"):
                    setattr(existing, name, value)
            report.updated["files"] += 1
    await s.flush()

    # ── the mount ──────────────────────────────────────────────────────────
    if workspace_code is not None:
        mount = await s.get(CodexMount, (codex_final, workspace_code))
        if mount is None:
            lowest = await s.scalar(select(func.min(CodexMount.sort)).where(CodexMount.workspace_code == workspace_code))
            s.add(CodexMount(codex_code=codex_final, workspace_code=workspace_code, enabled=True,
                             sort=SORT_DEFAULT if lowest is None else lowest - SORT_STEP))
            await s.flush()
        report.mounted = True

    await _check_depth(s, codex_final)


async def _bin_orphans(s, plan: ImportPlan, report: ImportReport, *, codex_final: str,
                       note_final: dict[str, str]) -> None:
    """A record the archive brings in the bin takes its live branch here along, under its mark.

    «Update» writes the archive's ``deleted_at`` over a live record here, and records the archive
    does not know stay where they were — a live child under a deleted parent, a state the codex
    service never makes: it deletes a branch whole, and a restore brings back what left with it.
    """
    binned = {note_final[row["code"]] for row in plan.content.notes if row.get("deleted_at") is not None}
    if not binned:
        return
    rows = (await s.execute(select(CodexNote).where(CodexNote.codex_code == codex_final))).scalars().all()
    children: dict[str, list[CodexNote]] = {}
    for row in rows:
        if row.parent_code is not None:
            children.setdefault(row.parent_code, []).append(row)
    by_code = {row.code: row for row in rows}
    for code in binned:
        mark = by_code[code].deleted_at
        stack = list(children.get(code, []))
        while stack:
            row = stack.pop()
            if row.deleted_at is None:
                row.deleted_at = mark
                report.binned.append({"code": f"{CODEX_CODE_PREFIX}@{row.code}", "title": row.title})
            stack.extend(children.get(row.code, []))
    await s.flush()


async def _check_depth(s, codex_code: str) -> None:
    rows = (await s.execute(select(CodexNote).where(CodexNote.codex_code == codex_code,
                                                     CodexNote.deleted_at.is_(None)))).scalars().all()
    parent = {row.code: row.parent_code for row in rows}
    for code in parent:
        level, cursor = 2, parent[code]
        while cursor is not None:
            level += 1
            cursor = parent.get(cursor)
            if level > DEPTH_MAX:
                # The plan withdraws «update» when updating everything breaks the levels; a mix of
                # «update» and «replace» can still do it — it is the choices, not the archive.
                raise TransferError(DEPTH_EXCEEDED, f"These choices would put {code} deeper than {DEPTH_MAX} levels",
                                    params={"record": f"{CODEX_CODE_PREFIX}@{code}", "levels": DEPTH_MAX})


def _recoded(plan: ImportPlan, codex_final: str, note_final: dict[str, str], file_code: dict[str, str]):
    content = plan.content
    found = []
    if codex_final != content.codex["code"]:
        found.append({"entity": "codex", "title": content.codex["title"],
                      "from": f"{CODEX_CODE_PREFIX}@{content.codex['code']}", "to": f"{CODEX_CODE_PREFIX}@{codex_final}"})
    titles = {row["code"]: row["title"] for row in content.notes}
    found += [{"entity": "record", "title": titles[old], "from": f"{CODEX_CODE_PREFIX}@{old}", "to": f"{CODEX_CODE_PREFIX}@{new}"}
              for old, new in note_final.items() if old != new]
    names = {row["binding"]["file_code"]: row["binding"].get("title") or row.get("name") or "" for row in content.files}
    found += [{"entity": "file", "title": names.get(old, ""), "from": f"{FILE_CODE_PREFIX}@{old}", "to": f"{FILE_CODE_PREFIX}@{new}"}
              for old, new in file_code.items() if old != new]
    return found


__all__ = ["ImportReport", "apply_plan", "free_segment"]
