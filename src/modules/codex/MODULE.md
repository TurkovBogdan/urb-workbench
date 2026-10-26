# codex

The module keeps codexes — development rules that do not depend on a project — and mounts them
into the workspaces of the projects that follow them.

A codex is a set of rules on one theme («Python backend», «Vue frontend»): a title, a line on when
to turn to it, the rules of working in it, and a tree of notes. The person creates codexes and
mounts them; the agent reads the mounted ones as one canvas and, where the mount allows it, writes
notes.

## Responsibility

Four entities:

| Entity | Table | Code | What it is |
| --- | --- | --- | --- |
| Codex | `codex` | `CODEX@` | the root: `segment`, `title`, `description` («when to turn to it»), `body` (the rules of working in it) |
| Codex note | `codex_note` | `CODEX@` | a record of the tree: text and children, like a page in Notion; no folder/document flag |
| Mount | `codex_mount` | — | a codex's entry in a workspace: its place in the workspace's order, `enabled` (switched on), `agent_can_edit` |
| Note file | `codex_file` | `FILE@` (the storage's code) | a file of `core_storage` a note holds: `title`, `description` (256 each, optional), `sort`; the holder is a note, never a codex |

A codex and a note share one prefix: the agent reaches both by one code, and a fresh code is
checked against both tables (`crud/code.py`). A path (`python/test/factories`) is the codex segment
plus the notes' segments; it is never stored, so a rename or a move rewrites one row.

## The service

What both surfaces build on — the person's HTTP API and the agent's tools in `workbench`. A broken
rule is a `ValueError` naming the rule and the numbers, raised before anything is written; a
missing row is `None` / `False`.

| File | Operations |
| --- | --- |
| `crud/codex.py` | `codex_create` / `get` / `get_by_segment` / `list` / `update` / `delete` / `restore` — a segment unique among live codexes; a restore is refused while the segment is taken |
| `crud/mount.py` | `mount_add` / `remove` (switch on / off — the row and its place stay) / `set_agent_can_edit` / `reorder` / `get` / `list` / `workspace_codexes` — the workspace's order covers every codex, switched on or not, and a switch never moves one; `mount_get` is the visibility check, `mount_list` the canvas |
| `crud/note.py` | `note_create` / `get` / `update` (fields, segment, `parent_code` move, `after_code` place) / `delete` (`with_branch`) / `restore` |
| `crud/read.py` | `resolve` (code or path in a workspace's canvas), `children_of` (with counts), `subtree`, `search` |
| `crud/file.py` | the binding rows: `codex_file_check` / `create` / `get` / `list` / `list_by_file` / `pairs` / `update` / `reorder` / `delete`, `codex_files_take` (inside a deletion's transaction) |
| `files.py` | a note's files: `codex_file_attach_spooled` (a file `core_storage_upload` spooled) / `_existing`, `codex_file_detach`, `codex_file_retitle`, `codex_file_views` — the storage step and the row step in two transactions, under the note's lock |
| `file_holders.py` | `CODEX@` of a note as the holder an upload goes to (`core_storage_upload`: the check before the body, the attach, the list row as the answer) |
| `file_owner.py` | the note as a storage owner, `("CODEX", <note code>, "")`, its file lock `note_files_lock`, and releasing it after a commit |
| `reconcile.py`, `tasks/file_owners_task.py` | the hourly reconciliation of the notes' storage owners with the binding rows |
| `rules.py` | the segment format, the depth limit, `agent_may_write` — one answer for both surfaces |

The tree rules the service holds: the parent is live and in the same codex; a move into another
codex carries the whole branch over, its deleted rows too, so their restore lands there (the
person's move — the agent's `codex_update` stays within one codex); a move never puts a note
under its own branch; four levels at most (`codex / note / note / note`), a moved branch
counted whole; a segment free among live siblings. A note with live children is deleted only with
its branch, under one mark that its restore follows. Structural writes serialise: `BEGIN
IMMEDIATE` on SQLite, plus one `pg_advisory_xact_lock` on PostgreSQL.

Reads see a workspace's canvas only — the live codexes mounted there. Search folds case in Python:
SQLite's `lower()` is ASCII-only. The person's pages also read one codex whole, mounted or not
(`codex_branch`, `note_node`).

A note's files go to the storage `public`, held by the note. The storage is never called from
inside a `write_scope` of ours — its own write transaction would wait on SQLite's lock — so a file
is attached in two steps: the checks, the storage, then the row; a refused row gives the owner
back. Every file operation of a note runs under the note's lock (`note_files_lock`), so an attach
and a detach of one note cannot interleave between those steps. The same bytes again: a note
holding the file refuses and nothing changes; a note whose binding stayed while the file manager
deleted the file gets it back, and the answer is that binding. A file of a store other than
`public` is refused (`codex.file.foreign_store`), and so is a title edit of a file the list hides.
A soft deletion of a note or a codex keeps the files for the restore: neither a deleted note nor
a note of a deleted codex takes, re-titles, reorders or gives up a file (`codex.codex.deleted`).
The CRUD's hard deletions, which no surface reaches, take the binding rows and release the owners
after the commit.

A failure between such a commit and its release leaves a live owner with no row. The scheduled
task `codex.file_owners` (hourly, `30 * * * *`, `reconcile.py`) releases those owners, under the
note's lock and after looking for the row again; a row whose file is live and whose owner is not
is logged as a warning and left as it is. A workspace's final deletion takes no note — notes
belong to a codex, and the cascade from `workspaces` reaches only the mounts — so the module
registers no purge hook.

## HTTP API

`api.py`, zone `internal`, prefix `/codex`:

| Route | What |
| --- | --- |
| `GET/POST /codexes`, `GET/PUT/DELETE /codexes/{code}`, `POST /codexes/{code}/restore` | codexes |
| `GET /codexes/{code}/tree` | a codex and its whole tree |
| `POST /notes`, `GET/PUT/DELETE /notes/{code}` (`?branch=true`), `POST /notes/{code}/move`, `POST /notes/{code}/restore` | notes |
| `GET /notes/{code}/files`, `PATCH/DELETE /notes/{code}/files/{file}`, `PUT /notes/{code}/files/order` | a note's files: the list, title and description, detaching, the whole order |
| `GET/POST /workspaces/{workspace}/mounts`, `PATCH/DELETE …/mounts/{code}`, `POST …/mounts/{code}/reorder` | the canvas of a workspace |

A foreign code — 400; no row — 404 with a code; a deleted row asked to change — 409 with a code; a
broken tree rule — 409 with the service's text. A note with children asked to go alone answers
409 `codex.note.has_children` with the children in `params`. The codes are translated in
`web/src/features/codex/locales`.

The person's upload is not here: it is `POST /storage/upload?holder=CODEX@<note>` of
`core_storage_upload`, which asks this module through `file_holders.py`. Its refusals keep this
module's codes — 400 `codex.file.holder_is_codex`, 404 `codex.note.not_found`, 409
`codex.note.deleted` / `codex.codex.deleted`, 409 `codex.file.already_attached` with `file`,
`name`, `type` in `params` — and the answer is the row of the note's list.

## Boundaries: what is not here

No agent surface. The `codex_*` tools, the `CODEX@` handlers of `content_*` / `delete` /
`interface_open` and every refusal text an agent reads belong to `workbench`.

No `notes`: a codex note lives in a tree and is reached by path, a document of `notes` has
neither. Moving a codex note into a task or into project documentation is a new record with a new
code.

Project documentation — the description of one project — is not a codex either: it belongs to one
workspace and is designed separately.

## Which way the dependency points

**Level 2**: on `workspace` (a mount names a workspace), the core and the platform modules
`core_storage` (its `services/`, `dto.py`, `errors.py` only) and `core_storage_upload` (its
holder registry). `workbench` builds on it.
`tests/apps/test_python_layer_boundaries.py` holds the levels.

## Storage

| Table | Keys and indexes | Revision |
| --- | --- | --- |
| `codex` | PK `code`; `ux_codex_segment` — unique among live rows | `cxm_001_codex` |
| `codex_note` | PK `code`; FK `codex_code`, `parent_code` (both `CASCADE`); `ck_codex_note_not_own_parent`; `ux_codex_note_parent_segment`, `ux_codex_note_top_segment` — a segment unique among live siblings; `ix_codex_note_parent_sort`, `ix_codex_note_codex_sort` | `cxm_002_codex_note` |
| `codex_mount` | PK (`codex_code`, `workspace_code`), both FK `CASCADE`; `ix_codex_mount_workspace_sort`; `enabled` | `cxm_003_codex_mount`, `cxm_004_codex_mount_enabled` |
| `codex_file` | PK (`note_code`, `file_code`); FK `note_code` → `codex_note`, `file_code` → `core_storage_file`, both `CASCADE`; `ix_codex_file_file_code` | `cxm_005_file` |

Segment uniqueness among siblings takes two partial indexes: a plain
`UNIQUE (parent_code, segment)` does not compare `NULL` with `NULL` on either provider, so the top
level gets its own index by codex. A soft-deleted row frees its segment.

`cxm_003_codex_mount` depends on `wkm_001_workspaces` and `cxm_005_file` on `csm_001_files` — the
revisions creating the FK targets, not the heads of their chains: a dependency on a head breaks the
overlap check.

`sort` — higher is higher up, 500 by default, step 5, as in `tasks`.

Every write goes through the ORM, so the change feed sees it: `codex.codex`, `codex.note` (refs —
the codex and the parent), `codex.mount` (ref — the workspace), `codex.file` (id — `FILE@`, ref —
the note).

## Contents

| File | What it holds |
| --- | --- |
| `module.py` | The declaration: name, migrations, the `internal` router at `/codex`, the feed entities |
| `api.py` | HTTP for the person's pages |
| `dto.py` | `CodexRow`, `NoteRow` (with its path), `TreeNode`, `MountRow`, `NoteFileRow` |
| `errors.py` | Refusal codes, translated in `web/src/features/codex/locales`; `CodexRuleError` carries one |
| `models/` | The ORM rows: `Codex`, `CodexNote`, `CodexMount`, `CodexFile` |
| `crud/` | The service — see above; `crud/code.py` — a fresh code, free in both tables |
| `files.py`, `file_owner.py` | A note's files: attaching through the storage, detaching, the owner |
| `rules.py` | What a tree may hold |
| `text.py` | `fit` — the length limit, refusing with the numbers |
| `codes.py` | Code generation and the `CODEX@` boundary prefix |
| `constants.py` | Code length, field sizes, list positions |
