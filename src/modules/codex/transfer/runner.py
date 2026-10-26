"""The two phases of a codex import: the analysis that cannot write, and the apply over a fresh plan."""

from __future__ import annotations

from pathlib import Path

from src.modules.codex.transfer.apply import ImportReport, apply_plan
from src.modules.codex.transfer.constants import CODEX_ARCHIVE, UPLOAD_CONSUMER
from src.modules.codex.transfer.plan import ImportPlan, build_plan
from src.modules.core_transfer.constants import MAX_UPLOAD_BYTES
from src.modules.core_transfer.conflicts import resolve_choices
from src.modules.core_transfer.container import ArchiveReader
from src.modules.core_transfer.errors import PLAN_CHANGED, TransferError
from src.modules.core_transfer.install import install_id
from src.modules.core_transfer.uploads import UploadArea

UPLOADS = UploadArea(UPLOAD_CONSUMER, CODEX_ARCHIVE.extension)


def _reader(path: Path) -> ArchiveReader:
    # Reading is bounded by what an upload may weigh; the storage's ceiling is the plan's, by name.
    return ArchiveReader(path, CODEX_ARCHIVE, max_file_bytes=MAX_UPLOAD_BYTES)


async def analyze_archive(path: Path) -> ImportPlan:
    with _reader(path) as reader:
        reader.open_manifest()
        reader.verify_inventory()
        return await build_plan(reader, install=await install_id())


async def import_archive(
    path: Path, *, workspace_code: str | None, decisions: dict[str, str], plan_token: str
) -> tuple[ImportPlan, ImportReport]:
    with _reader(path) as reader:
        reader.open_manifest()
        reader.verify_inventory()
        plan = await build_plan(reader, install=await install_id())
        if plan.token != plan_token:
            raise TransferError(PLAN_CHANGED, "The base changed since the plan was shown — analyse again")
        choices = resolve_choices(plan.conflicts, decisions)
        return plan, await apply_plan(reader, plan, choices, workspace_code=workspace_code)


__all__ = ["UPLOADS", "analyze_archive", "import_archive"]
