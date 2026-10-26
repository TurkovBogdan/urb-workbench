"""The plan of a codex import: the archive's tree checked, every entity judged — before a write.

One code space covers two tables: a code is taken when a codex OR a record holds it, deleted
ones too. What may be done about a taken code:

- the codex — «update» or «replace» when a codex holds the code (a codex belongs to no workspace,
  so nothing forbids writing over it); «replace» only when a record holds it;
- a record of the target codex — «update» (with its codex) or «replace»; of another codex, or a
  code a codex holds — «replace» only;
- a file — by «code + sha256», as for a task (``core_transfer.files``).

«Update» of the codex is withdrawn when the merged tree would break the four levels: a record
moved by the archive taking along local children the archive does not know.

Segments are not codes: a taken one gets a suffix at the apply, and the plan names the definite
ones up front.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from src.core.utils.date import datetime_to_agent
from src.modules.codex.constants import BODY_MAX, CODEX_CODE_PREFIX, FILE_CODE_PREFIX, FILE_STORE
from src.modules.codex.crud import transfer as transfer_crud
from src.modules.codex.models import Codex, CodexFile, CodexNote
from src.modules.codex.rules import DEPTH_MAX, segment_problem
from src.modules.codex.transfer.constants import (
    ENTITY_CODEX,
    ENTITY_FILES,
    ENTITY_NOTES,
    REASON_CODE_IS_CODEX,
    REASON_CODE_IS_RECORD,
    REASON_DEPTH_EXCEEDED,
    REASON_FILE_OTHER_CONTENT,
    REASON_PARENT_REPLACED,
    REASON_RECORD_OTHER_CODEX,
    codex_body_entry,
    file_entry,
    note_body_entry,
    rows_entry,
)
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

_CODE = re.compile(r"^[0-9A-F]{10}$")
_SHA = re.compile(r"^[0-9a-f]{64}$")
# How deep a deleted branch may lie: moves stack it below four levels, a crafted archive could stack
# it without end.
_BIN_DEPTH_MAX = 16
# A body is at most ``BODY_MAX`` characters, four bytes each at most in UTF-8: a larger entry is not
# one this application wrote, and it is not read into memory.
BODY_BYTES_MAX = 4 * BODY_MAX


def _inconsistent(detail: str) -> TransferError:
    return TransferError(ARCHIVE_INCONSISTENT, f"The archive contradicts itself: {detail}", params={"detail": detail})


def _code(value: Any, what: str) -> str:
    if not isinstance(value, str) or not _CODE.match(value):
        raise _inconsistent(f"{what} is not a code: {value!r}")
    return value


def _require_body(reader: ArchiveReader, entry: str, what: str) -> None:
    inventory = reader.inventory_of(entry)
    if inventory is None:
        raise _inconsistent(f"{what} has no body")
    if inventory.bytes > BODY_BYTES_MAX:
        raise _inconsistent(f"the body of {what} is larger than any body this application writes")


def _stamp(value: datetime | None) -> str | None:
    return datetime_to_agent(value) if value is not None else None


@dataclass
class ArchiveContent:
    manifest: Manifest
    codex: dict[str, Any]
    notes: list[dict[str, Any]]
    files: list[dict[str, Any]]
    depth: dict[str, int]

    def archived_files(self) -> dict[str, ArchivedFile]:
        found: dict[str, ArchivedFile] = {}
        for row in self.files:
            code = row["binding"]["file_code"]
            found.setdefault(code, ArchivedFile(
                code=code, sha256=row["stored"]["sha256"], size=int(row["stored"]["size"]),
                entry=row["entry"], filename=str(row.get("name") or ""),
            ))
        return found


def read_content(reader: ArchiveReader) -> ArchiveContent:
    manifest = reader.manifest or reader.open_manifest()
    rows = reader.rows(rows_entry(ENTITY_CODEX))
    if len(rows) != 1 or rows[0].get("code") != manifest.root.code:
        raise _inconsistent("the codex row is not the manifest's root")
    codex = rows[0]
    root = _code(codex["code"], "the codex")
    if segment_problem(str(codex.get("segment") or "")) or not str(codex.get("title") or "").strip():
        raise _inconsistent("the codex has no valid segment or title")
    _require_body(reader, codex_body_entry(root), "the codex")

    notes = reader.rows(rows_entry(ENTITY_NOTES))
    depth: dict[str, int] = {}
    live_chain: dict[str, bool] = {}
    live_segments: set[tuple[str | None, str]] = set()
    for row in notes:
        code = _code(row.get("code"), "a record")
        if code == root or code in depth:
            raise _inconsistent(f"the record {code} comes twice or is the codex")
        if row.get("codex_code") != root:
            raise _inconsistent(f"the record {code} is of another codex")
        parent = row.get("parent_code")
        if parent is not None and parent not in depth:
            raise _inconsistent(f"the parent of record {code} is not before it")
        level = 2 if parent is None else depth[parent] + 1
        # The four levels bind the live tree. A deleted branch moved along with its live parent can
        # lie deeper — the codex service counts only the live height — and its bin must travel too.
        live_chain[code] = row.get("deleted_at") is None and (parent is None or live_chain[parent])
        if live_chain[code] and level > DEPTH_MAX:
            raise _inconsistent(f"the record {code} is deeper than {DEPTH_MAX} levels")
        if level > _BIN_DEPTH_MAX:
            raise _inconsistent(f"the record {code} lies {level} levels deep")
        segment = str(row.get("segment") or "")
        if segment_problem(segment) or not str(row.get("title") or "").strip():
            raise _inconsistent(f"the record {code} has no valid segment or title")
        if row.get("deleted_at") is None:
            if (parent, segment) in live_segments:
                raise _inconsistent(f"the segment {segment!r} comes twice among live siblings")
            live_segments.add((parent, segment))
        _require_body(reader, note_body_entry(code), f"the record {code}")
        depth[code] = level

    files = reader.rows(rows_entry(ENTITY_FILES))
    pairs: set[tuple[str, str]] = set()
    content_of: dict[str, str] = {}
    code_of: dict[str, str] = {}
    for row in files:
        binding, stored = row.get("binding") or {}, row.get("stored") or {}
        code = _code(binding.get("file_code"), "a file")
        note = _code(binding.get("note_code"), f"the record of file {code}")
        if note not in depth or (note, code) in pairs:
            raise _inconsistent(f"the file {code} is not of an archived record or comes twice in it")
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
        # The claimed sum decides which file here is taken by content — trusted only as the bytes' own.
        inventory = reader.inventory_of(row["entry"])
        if inventory is None or inventory.sha256 != sha or inventory.bytes != size:
            raise _inconsistent(f"the file {code} claims another content than its bytes")
        pairs.add((note, code))

    check_rows(Codex, [codex], omit=("body",))
    check_rows(CodexNote, notes, omit=("body",))
    check_rows(CodexFile, [row["binding"] for row in files])

    return ArchiveContent(manifest=manifest, codex=codex, notes=notes, files=files, depth=depth)


@dataclass
class ImportPlan:
    content: ArchiveContent
    same_install: bool
    conflicts: list[Conflict]
    local_codexes: dict[str, Codex]
    local_notes: dict[str, CodexNote]
    verdicts: dict[str, FileVerdict]
    recoded: list[dict[str, str]] = field(default_factory=list)
    repathed: list[dict[str, str]] = field(default_factory=list)

    @property
    def token(self) -> str:
        notices = [f"{r['entity']}:{r['from']}>{r['to']}" for r in self.recoded]
        notices += [f"path:{r['from']}>{r['to']}" for r in self.repathed]
        return plan_token(self.conflicts, notices)


async def build_plan(reader: ArchiveReader, *, install: str) -> ImportPlan:
    content = read_content(reader)
    root = content.codex["code"]
    codes = [root, *(row["code"] for row in content.notes)]
    local_codexes, local_notes = await transfer_crud.code_holders(codes)
    verdicts = await judge_files(content.archived_files().values(), store=FILE_STORE)
    refuse_over_ceiling(verdicts.values())
    conflicts: list[Conflict] = []

    codex_conflict: Conflict | None = None
    codex_id = f"{CODEX_CODE_PREFIX}@{root}"
    archive_side = Side(updated_at=content.codex.get("updated_at"), created_at=content.codex.get("created_at"))
    if root in local_codexes:
        local = local_codexes[root]
        described = {"kind": "codex", "code": codex_id, "title": local.title, "path": f"/{local.segment}",
                     "deleted": "1" if local.deleted_at is not None else ""}
        here = Side(updated_at=_stamp(local.updated_at), created_at=_stamp(local.created_at))
        depth_issue = await _depth_issue(content, local_notes, root)
        if depth_issue:
            codex_conflict = only_replace(codex_id, "codex", content.codex["title"], described, here=here,
                                          archive=archive_side, reason=REASON_DEPTH_EXCEEDED,
                                          reason_params={"records": depth_issue})
        else:
            codex_conflict = both_ways(codex_id, "codex", content.codex["title"], described, here=here,
                                       archive=archive_side)
    elif root in local_notes:
        local_note = local_notes[root]
        codex_conflict = only_replace(
            codex_id, "codex", content.codex["title"],
            {"kind": "record", "code": codex_id, "title": local_note.title},
            here=Side(updated_at=_stamp(local_note.updated_at), created_at=_stamp(local_note.created_at)),
            archive=archive_side, reason=REASON_CODE_IS_RECORD,
        )
    if codex_conflict is not None:
        conflicts.append(codex_conflict)

    codex_titles = {code: row.title for code, row in (await transfer_crud.rows_by_codes(
        Codex, (note.codex_code for note in local_notes.values()))).items()}
    for row in content.notes:
        code = row["code"]
        conflict_id = f"{CODEX_CODE_PREFIX}@{code}"
        archive = Side(updated_at=row.get("updated_at"), created_at=row.get("created_at"))
        if code in local_codexes:
            local_codex = local_codexes[code]
            conflicts.append(only_replace(
                conflict_id, "record", row["title"],
                {"kind": "codex", "code": conflict_id, "title": local_codex.title, "path": f"/{local_codex.segment}",
                 "deleted": "1" if local_codex.deleted_at is not None else ""},
                here=Side(updated_at=_stamp(local_codex.updated_at), created_at=_stamp(local_codex.created_at)),
                archive=archive, reason=REASON_CODE_IS_CODEX,
            ))
            continue
        local = local_notes.get(code)
        if local is None:
            continue
        here = Side(updated_at=_stamp(local.updated_at), created_at=_stamp(local.created_at))
        described = {
            "kind": "record", "code": conflict_id, "title": local.title,
            "holder": f"{CODEX_CODE_PREFIX}@{local.codex_code}", "holder_title": codex_titles.get(local.codex_code, ""),
            "deleted": "1" if local.deleted_at is not None else "",
        }
        if local.codex_code != root:
            conflicts.append(only_replace(conflict_id, "record", row["title"], described, here=here, archive=archive,
                                          reason=REASON_RECORD_OTHER_CODEX,
                                          reason_params={"codex": described["holder_title"]}))
        elif codex_conflict is None or "update" not in codex_conflict.options:
            conflicts.append(only_replace(conflict_id, "record", row["title"], described, here=here, archive=archive,
                                          reason=REASON_PARENT_REPLACED))
        else:
            conflicts.append(both_ways(conflict_id, "record", row["title"], described, here=here, archive=archive,
                                       requires=(codex_conflict.id, "update")))

    for code, verdict in verdicts.items():
        if verdict.outcome != FILE_CONFLICT:
            continue
        row = next(row for row in content.files if row["binding"]["file_code"] == code)
        local_file = verdict.local
        conflicts.append(only_replace(
            f"{FILE_CODE_PREFIX}@{code}", "file", row["binding"].get("title") or row.get("name") or code,
            {"kind": "file", "code": f"{FILE_CODE_PREFIX}@{code}", "title": "", "mime": local_file.mime if local_file else ""},
            here=Side(created_at=_stamp(local_file.created_at) if local_file else None,
                      size=local_file.size if local_file else None),
            archive=Side(updated_at=row["binding"].get("updated_at"), created_at=row["stored"].get("created_at"),
                         size=int(row["stored"]["size"])),
            reason=REASON_FILE_OTHER_CONTENT,
        ))

    recoded = []
    for code, verdict in verdicts.items():
        if verdict.outcome == FILE_RECODE and verdict.local is not None:
            row = next(row for row in content.files if row["binding"]["file_code"] == code)
            recoded.append({"entity": "file", "title": row["binding"].get("title") or row.get("name") or "",
                            "from": f"{FILE_CODE_PREFIX}@{code}", "to": f"{FILE_CODE_PREFIX}@{verdict.local.code}"})

    repathed = []
    segments = await transfer_crud.live_codex_segments()
    holder = segments.get(content.codex["segment"])
    if content.codex.get("deleted_at") is None and holder is not None and holder != root:
        repathed.append({"entity": "codex", "title": content.codex["title"],
                         "from": f"/{content.codex['segment']}", "to": ""})

    return ImportPlan(
        content=content,
        same_install=bool(content.manifest.source.install_id) and content.manifest.source.install_id == install,
        conflicts=conflicts,
        local_codexes=local_codexes,
        local_notes=local_notes,
        verdicts=verdicts,
        recoded=recoded,
        repathed=repathed,
    )


async def _depth_issue(content: ArchiveContent, local_notes: dict[str, CodexNote], root: str) -> str:
    """Records here the archive does not know that the merged tree would push past four levels."""
    archived = {row["code"]: row.get("parent_code") for row in content.notes}
    here = await transfer_crud.notes_of(root)
    parent: dict[str, str | None] = {row.code: row.parent_code for row in here if row.deleted_at is None}
    parent.update(archived)
    too_deep = []
    for code in parent:
        level, cursor, seen = 2, parent.get(code), {code}
        while cursor is not None and cursor not in seen:
            seen.add(cursor)
            level += 1
            cursor = parent.get(cursor)
        if level > DEPTH_MAX and code not in archived:
            too_deep.append(code)
    return ", ".join(f"{CODEX_CODE_PREFIX}@{code}" for code in sorted(too_deep))


def plan_body(plan: ImportPlan, *, file_name: str, size: int) -> dict[str, Any]:
    manifest = plan.content.manifest
    codex = plan.content.codex
    return {
        "archive": {
            "file_name": file_name,
            "size": size,
            "created_at": manifest.created_at,
            "app_version": manifest.source.app_version,
            "format_version": manifest.format_version,
            "same_install": plan.same_install,
        },
        "root": {
            "code": f"{CODEX_CODE_PREFIX}@{codex['code']}",
            "title": codex["title"],
            "path": f"/{codex['segment']}",
            # A codex exported from the bin comes in the bin and holds no path.
            "deleted": codex.get("deleted_at") is not None,
        },
        "counts": {
            "notes": len(plan.content.notes),
            "deleted_notes": sum(1 for row in plan.content.notes if row.get("deleted_at") is not None),
            "files": len(plan.content.archived_files()),
        },
        "conflicts": [conflict.as_dict() for conflict in plan.conflicts],
        "notices": {
            "recoded": plan.recoded,
            "repathed": plan.repathed,
            "dangling_refs": list(manifest.dangling_refs),
        },
        "plan_token": plan.token,
    }


__all__ = ["ArchiveContent", "ImportPlan", "build_plan", "plan_body", "read_content"]
