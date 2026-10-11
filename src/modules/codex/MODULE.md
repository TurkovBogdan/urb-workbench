# codex

The module keeps codexes — development rules that do not depend on a project — and mounts them
into the workspaces of the projects that follow them.

A codex is a set of rules on one theme («Python backend», «Vue frontend»): a title, a line on when
to turn to it, the rules of working in it, and a tree of notes. The person creates codexes and
mounts them; the agent reads the mounted ones as one canvas and, where the mount allows it, writes
notes.

## Responsibility

Three entities:

| Entity | Table | Code | What it is |
| --- | --- | --- | --- |
| Codex | `codex` | `CODEX@` | the root: `slug`, `title`, `description` («when to turn to it»), `body` (the rules of working in it) |
| Codex note | `codex_note` | `CODEX@` | a record of the tree: text and children, like a page in Notion; no folder/document flag |
| Mount | `codex_mount` | — | which workspace sees which codex, its place there, and `agent_can_edit` |

A codex and a note share one prefix: the agent reaches both by one code, and a fresh code is
checked against both tables (`crud/code.py`). A path (`python/test/factories`) is the codex slug
plus the notes' slugs; it is never stored, so a rename or a move rewrites one row.

## The service

What both surfaces build on — the person's HTTP API and the agent's tools in `workbench`. A broken
rule is a `ValueError` naming the rule and the numbers, raised before anything is written; a
missing row is `None` / `False`.

| File | Operations |
| --- | --- |
| `crud/codex.py` | `codex_create` / `get` / `get_by_slug` / `list` / `update` / `delete` / `restore` — a slug unique among live codexes; a restore is refused while the slug is taken |
| `crud/mount.py` | `mount_add` / `remove` / `set_agent_can_edit` / `reorder` / `get` / `list` — live codex into live workspace, once; `mount_get` is the visibility check, `mount_list` the canvas |
| `crud/note.py` | `note_create` / `get` / `update` (fields, slug, `parent_code` move, `after_code` place) / `delete` (`with_branch`) / `restore` |
| `crud/read.py` | `resolve` (code or path in a workspace's canvas), `children_of` (with counts), `subtree`, `search` |
| `rules.py` | the slug format, the depth limit, `agent_may_write` — one answer for both surfaces |

The tree rules the service holds: the parent is live and in the same codex; a move never puts a
note under its own branch; four levels at most (`codex / note / note / note`), a moved branch
counted whole; a slug free among live siblings. A note with live children is deleted only with
its branch, under one mark that its restore follows. Structural writes serialise: `BEGIN
IMMEDIATE` on SQLite, plus one `pg_advisory_xact_lock` on PostgreSQL.

Reads see a workspace's canvas only — the live codexes mounted there. Search folds case in Python:
SQLite's `lower()` is ASCII-only. The person's pages also read one codex whole, mounted or not
(`codex_branch`, `note_node`).

## HTTP API

`api.py`, zone `internal`, prefix `/codex`:

| Route | What |
| --- | --- |
| `GET/POST /codexes`, `GET/PUT/DELETE /codexes/{code}`, `POST /codexes/{code}/restore` | codexes |
| `GET /codexes/{code}/tree` | a codex and its whole tree |
| `POST /notes`, `GET/PUT/DELETE /notes/{code}` (`?branch=true`), `POST /notes/{code}/move`, `POST /notes/{code}/restore` | notes |
| `GET/POST /workspaces/{workspace}/mounts`, `PATCH/DELETE …/mounts/{code}`, `POST …/mounts/{code}/reorder` | the canvas of a workspace |

A foreign code — 400; no row — 404 with a code; a deleted row asked to change — 409 with a code; a
broken tree rule — 409 with the service's text. A note with children asked to go alone answers
409 `codex.note.has_children` with the children in `params`. The codes are translated in
`web/src/features/codex/locales`.

## Boundaries: what is not here

No agent surface. The `codex_*` tools, the `CODEX@` handlers of `content_*` / `delete` /
`interface_open` and every refusal text an agent reads belong to `workbench`.

No `notes`: a codex note lives in a tree and is reached by path, a document of `notes` has
neither. Moving a codex note into a task or into project documentation is a new record with a new
code.

Project documentation — the description of one project — is not a codex either: it belongs to one
workspace and is designed separately.

## Which way the dependency points

**Level 2**: on `workspace` (a mount names a workspace) and the core. `workbench` builds on it.
`tests/apps/test_python_layer_boundaries.py` holds the levels.

## Storage

| Table | Keys and indexes | Revision |
| --- | --- | --- |
| `codex` | PK `code`; `ux_codex_slug` — unique among live rows | `cxm_001_codex` |
| `codex_note` | PK `code`; FK `codex_code`, `parent_code` (both `CASCADE`); `ck_codex_note_not_own_parent`; `ux_codex_note_parent_slug`, `ux_codex_note_top_slug` — a slug unique among live siblings; `ix_codex_note_parent_sort`, `ix_codex_note_codex_sort` | `cxm_002_codex_note` |
| `codex_mount` | PK (`codex_code`, `workspace_code`), both FK `CASCADE`; `ix_codex_mount_workspace_sort` | `cxm_003_codex_mount` |

Slug uniqueness among siblings takes two partial indexes: a plain `UNIQUE (parent_code, slug)`
does not compare `NULL` with `NULL` on either provider, so the top level gets its own index by
codex. A soft-deleted row frees its slug.

`cxm_003_codex_mount` depends on `wkm_001_workspaces` — the revision creating the FK target, not
the head of its chain: a dependency on a head breaks the overlap check.

`sort` — higher is higher up, 500 by default, step 5, as in `tasks`.

Every write goes through the ORM, so the change feed sees it: `codex.codex`, `codex.note` (refs —
the codex and the parent), `codex.mount` (ref — the workspace).

## Contents

| File | What it holds |
| --- | --- |
| `module.py` | The declaration: name, migrations, the `internal` router at `/codex`, the feed entities |
| `api.py` | HTTP for the person's pages |
| `dto.py` | `CodexRow`, `NoteRow` (with its path), `TreeNode`, `MountRow` |
| `errors.py` | Refusal codes, translated in `web/src/features/codex/locales` |
| `models/` | The ORM rows: `Codex`, `CodexNote`, `CodexMount` |
| `crud/` | The service — see above; `crud/code.py` — a fresh code, free in both tables |
| `rules.py` | What a tree may hold |
| `text.py` | `fit` — the length limit, refusing with the numbers |
| `codes.py` | Code generation and the `CODEX@` boundary prefix |
| `constants.py` | Code length, field sizes, list positions |
