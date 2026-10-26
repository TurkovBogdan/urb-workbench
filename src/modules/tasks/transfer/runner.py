"""The two phases of a task import from outside: the analysis that cannot write, and the apply.

The analysis is physically unable to write — it is another function — so «the base does not
change until the button» is held by structure, not by discipline. The apply builds the plan anew
rather than keeping the one shown: between the two requests the person was thinking and the agent
may have written; the conflicts it finds must be the ones the person chose for (``plan_token``).
"""

from __future__ import annotations

from pathlib import Path

from src.modules.core_transfer.constants import MAX_UPLOAD_BYTES
from src.modules.core_transfer.conflicts import resolve_choices
from src.modules.core_transfer.container import ArchiveReader
from src.modules.core_transfer.errors import PLAN_CHANGED, TransferError
from src.modules.core_transfer.install import install_id
from src.modules.core_transfer.uploads import UploadArea
from src.modules.tasks.transfer.apply import ImportReport, apply_plan
from src.modules.tasks.transfer.constants import TASK_ARCHIVE, UPLOAD_CONSUMER
from src.modules.tasks.transfer.plan import ImportPlan, build_plan

UPLOADS = UploadArea(UPLOAD_CONSUMER, TASK_ARCHIVE.extension)


def _reader(path: Path) -> ArchiveReader:
    # Reading is bounded by what an upload may weigh; the storage's own ceiling is the plan's to
    # check, file by file and by name — rows carry the size the inventory proved.
    return ArchiveReader(path, TASK_ARCHIVE, max_file_bytes=MAX_UPLOAD_BYTES)


async def analyze_archive(path: Path, *, workspace_code: str) -> ImportPlan:
    """Read the archive and say what would become of the base; nothing is written."""
    with _reader(path) as reader:
        reader.open_manifest()
        reader.verify_inventory()
        return await build_plan(reader, workspace_code=workspace_code, install=await install_id())


async def import_archive(
    path: Path,
    *,
    workspace_code: str,
    group_code: str | None,
    decisions: dict[str, str],
    plan_token: str,
) -> tuple[ImportPlan, ImportReport]:
    """Check again, plan again over the base as it is now, and apply with the person's choices."""
    with _reader(path) as reader:
        reader.open_manifest()
        reader.verify_inventory()
        plan = await build_plan(reader, workspace_code=workspace_code, install=await install_id())
        if plan.token != plan_token:
            raise TransferError(PLAN_CHANGED, "The base changed since the plan was shown — analyse again")
        choices = resolve_choices(plan.conflicts, decisions)
        return plan, await apply_plan(reader, plan, choices, group_code=group_code)


__all__ = ["UPLOADS", "analyze_archive", "import_archive"]
