# notes

The module keeps documents — a title, what the document is about, and the markdown text — and
hands them to the modules that use them.

A note does not know where it is used. A task keeps its planning documents, a project its
documentation, a knowledge base its tree, and each of them holds the link itself. So one document
can move from a task to the project's documentation with the same code, and every reference to it
in plans and journals keeps working.

## Responsibility

One entity — the note — and the service over it, for the modules above:

| Operation | Function | What it does |
| --- | --- | --- |
| create | `note_create` | `title`, `description`, `body`; nothing is asked about an owner |
| get | `note_get` | one note whole; a deleted one only with `include_deleted` |
| get many | `note_get_many` | notes by codes, in the order given, **without `body`** — for a consumer's list |
| update | `note_update` | `title`, `description`, `body` — only what is passed; `body` is whole |
| delete | `note_delete(code, hard=False)` | soft by default; `hard=True` removes the row |
| restore | `note_restore` | clears the deletion mark |

Over a limit is refused with the numbers, never cut — the end of a document is where its point or
its file list sits. A refused write leaves the note as it was.

The HTTP API is the document page only: `GET` and `PUT /internal/notes/{code}`. Creating, listing
and deleting belong to the consumers: only they know where a note is going.

## Boundaries: what is not here

No owner, workspace, parent, position, kind or author. Those are properties of a use, and every
use is a different module's table. The boundary has been crossed if this module's code mentions an
entity of another module: an import from `src.modules.tasks`, a `task_code` column, the word
"task" in a response.

Not here yet, each its own piece of work: versions and protection against concurrent edits,
search. The agent's tools belong to the consumers — `tasks` has `task_note_*`.

## Which way the dependency points

The module sits at **level 1**, next to `workspace`: it depends on the core and the infrastructure
modules (the change feed) and on no application module. A consumer keeps `note_code` in its own
link table with `ON DELETE CASCADE`, so a hard delete takes the links along without this module
knowing who held them.

`tests/modules/notes/test_boundaries.py` checks the imports; `BASE_MODULES` in
`tests/apps/test_web_layer_boundaries.py` is the same rule for the frontend.

## Storage and codes

| Table | Columns | Revisions |
| --- | --- | --- |
| `notes` | `code` (PK, hex of length `CODE_LEN`), `title` (128), `description` (512), `body` (65536), `deleted_at`, `created_at`, `updated_at` | `ntm_001_notes` — the table, `ntm_002_notes_list_index` — `ix_notes_deleted_updated` for the list of every document |

One table — `notes`, without the module-name prefix: the module and the entity are one.

The table is the target of the consumers' FKs, and `depends_on` may only point at a revision
that is not the head of its chain. So the creating revision is buried under the next one, the
same split `workspace` has between `wkm_001` and `wkm_002`: a consumer depends on
`ntm_001_notes`, never on the head.

## Consumers

| Module | Link table | What a note is there |
| --- | --- | --- |
| `tasks` | `tasks_note` (`note_code` PK) | a task note: created with its task, belongs to that one task |

A consumer that creates a note together with its link passes its own write transaction to
`note_create(session=…)`: a refused link then leaves no note behind.

The database holds the bare hex code in upper case. `NOTE@` is added at the boundary and stripped
on input, in any case (`codes.py`, a copy of its own — the module cannot import a neighbour's); a
code with a foreign prefix is a mixed-up argument, and the API answers it with 400.

Every write goes through the ORM, so the change feed sees it: `notes.note`, created / updated /
deleted. A soft delete and a restore arrive as `updated`.

## Contents

| File | What it holds |
| --- | --- |
| `module.py` | The declaration: name, migrations, the `internal` router at `/notes`, the feed entity |
| `api.py` | HTTP: `GET` and `PUT` of one note |
| `crud/note.py` | The service consumers build on |
| `models/note.py` | The ORM row of `notes` |
| `dto.py` | `NoteRow` (whole) and `NoteSummaryRow` (without `body`) |
| `codes.py` | Code generation and the `NOTE@` boundary prefix |
| `constants.py` | Code length and field sizes — one source for the model, the CRUD and the HTTP bodies |
| `text.py` | `fit` — the length limit, refusing with the numbers |
| `errors.py` | Refusal codes, translated in `web/src/features/notes/locales` |
