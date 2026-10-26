"""The ``codex`` module — development rules shared across projects, mounted into workspaces.

**Level 2**: depends on ``workspace`` alone (a mount names a workspace), on the core and on the
platform module ``core_storage`` (the files of its notes). It owns
the rows and, as they arrive, the rules of what may happen to them and the person's HTTP API. It
holds no agent-surface code: the ``codex_*`` tools and the ``CODEX@`` handlers of the shared
methods live in ``workbench``.

Four tables, built by the ``cxm_*`` migrations on portable types — the chain runs on SQLite and
PostgreSQL: ``codex`` (the codex itself and its rules), ``codex_note`` (its tree of notes),
``codex_mount`` (which workspace sees which codex, and whether the agent may write there) and
``codex_file`` (which files of ``core_storage`` a note holds, under which title). The
module does not use ``notes``: a codex note lives in a tree and is reached by path, and a document
with no owner has neither.
"""

from __future__ import annotations

from pathlib import Path
from typing import ClassVar

from fastapi import FastAPI

from src.core.config import Config
from src.core.module import Module
from src.core.scheduler.registry import get_registry
from src.modules.codex import models
from src.modules.codex.api import router
from src.modules.codex.constants import CODEX_CODE_PREFIX, FILE_CODE_PREFIX
from src.modules.codex.file_holders import register_file_holders
from src.modules.codex.lookup import codex_preview
from src.modules.codex.tasks.file_owners_task import FileOwnersTask
from src.modules.core_changes import ChangeEntity, Code, register_entity
from src.modules.core_lookup import LookupType, register_type
from src.modules.workspace.constants import WORKSPACE_CODE_PREFIX

# What the change feed sees of this module. The names are a public contract with the frontend;
# the refs are what a screen recognises "this is about me" by: the codex page by its codex, a
# note's children by their parent, a workspace's canvas by the workspace. A mount has no code of
# its own — it is named by the codex it mounts.
CHANGE_ENTITIES = (
    ChangeEntity("codex.codex", models.Codex, id=Code("code", CODEX_CODE_PREFIX)),
    ChangeEntity(
        "codex.note",
        models.CodexNote,
        id=Code("code", CODEX_CODE_PREFIX),
        refs=(Code("codex_code", CODEX_CODE_PREFIX), Code("parent_code", CODEX_CODE_PREFIX)),
    ),
    ChangeEntity(
        "codex.mount",
        models.CodexMount,
        id=Code("codex_code", CODEX_CODE_PREFIX),
        refs=(Code("workspace_code", WORKSPACE_CODE_PREFIX),),
    ),
    # A file's binding to a note, named by the file; the note's page knows it by the note.
    ChangeEntity(
        "codex.file",
        models.CodexFile,
        id=Code("file_code", FILE_CODE_PREFIX),
        refs=(Code("note_code", CODEX_CODE_PREFIX),),
    ),
)

_HERE = Path(__file__).resolve().parent


class CodexModule(Module):
    name: ClassVar[str] = "codex"
    description: ClassVar[str] = "Codex: development rules shared across projects."
    migrations_dir = _HERE / "migrations" / "versions"
    internal_router = router
    internal_router_prefix = "/codex"

    def configure(self, app: FastAPI, config: Config) -> None:
        """Tell the change feed about codexes, notes and mounts; answer for ``CODEX@`` in the
        lookup; schedule the reconciliation of the notes' storage owners (``FileOwnersTask``); read
        ``CODEX@`` of a note as the holder of a served file and of an upload (``file_holders``).

        No hook for a workspace's final deletion: notes belong to a codex, not to a workspace,
        and the cascade from ``workspaces`` takes only the mounts — no note, no file binding.
        """
        for entity in CHANGE_ENTITIES:
            register_entity(entity)
        register_type(LookupType(CODEX_CODE_PREFIX, codex_preview))
        register_file_holders()
        if get_registry().get(FileOwnersTask.MODULE, FileOwnersTask.CODE) is None:
            FileOwnersTask.register()


__all__ = ["CHANGE_ENTITIES", "CodexModule"]
