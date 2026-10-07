# workspace

The module creates workspaces and hands them to the rest: every module above narrows its queries
to the workspace the human is working in right now.

A workspace answers one question — "what am I working in right now" — and separates what must not
mix: work and personal, one client and another. There are no access rights here: there is one
user, and a workspace divides contexts, not access.

## Responsibility

The module holds one entity — the workspace card — and one extension point for it.

Its job: create a workspace, read it, rename it, delete it, bring it back from the deleted, and
build the list with content counters. A human edits all of this, so the set of endpoints is
complete: a workspace is the human's layout, not the product of the agent's work.

## Boundaries: what is not here

What lives inside a workspace the module does not know and must not know. Zones and tasks are
the business of `tasks`; documents will be the business of whichever module introduces documents.

The boundary has been crossed if the module's code mentions another module's entity: an import
from `src.modules.tasks`, an `area_code` column, the word "task" in an API response. Any one is
enough.

## Which way the dependency points

The module sits at **level 1**: it depends on the core and on no application module.
Application modules — level 2 and above — keep `workspace_code` on their rows.

The dependency runs bottom-up and one way only: those above know about the workspace, it does
not know about them. Reverse it, and level 1 would depend on level 2, and the application would
no longer assemble in the declared order (`src/apps/app/modules.py`).

## Counters: how other modules' numbers get onto the card

The workspace card shows numbers: "2 zones, 12 tasks". The same numbers are assembled into a line
in the delete dialog — "the workspace holds zones: 2, tasks: 12. Delete?". That question is why
counters exist: `purge` removes the contents irreversibly, and a human should not have to confirm
the disappearance of who knows what.

The module cannot get these numbers itself. Zones and tasks belong to `tasks`, and querying its
tables would reverse the dependency — see the section above. So the entity's owner does the
counting and brings the result itself:

```python
# tasks/module.py, configure() — once per application build
register_counter(WorkspaceCounter(
    key="areas",                                  # the number goes into the response under this key
    label_key="tasks.workspace.counter.areas",    # the label from its OWN dictionary
    count_by_codes=area_crud.area_count_by_workspace_codes,
    sort=600,                                     # higher — earlier on the card
))
```

The workspace calls whatever was left for it and does not know what was counted. Hence the key
property: the set of numbers in the response depends on the application's composition. Remove
`tasks` from the build and the counters disappear — and the card is right, not broken.

Two details that are easy to get wrong:

- **Count in a batch.** The function takes a list of codes and returns `{code: how many}`. A
  query per card would make N+1 where a single grouping is enough.
- **The label travels as a key, not text.** It is owned by whoever owns the entity: renaming
  "zones" is done in `tasks`, not in a module that knows nothing about zones.

## Storage and codes

| Table | Columns | Indexes | Revisions |
| --- | --- | --- | --- |
| `workspaces` | `code` (PK, hex of length `CODE_LEN`), `title`, `description`, `color`, `icon`, `sort`, `deleted_at`, `created_at`, `updated_at` | `ix_workspaces_deleted_sort` (`deleted_at`, `sort`, `title`, `code`) — mirrors the list query | `wkm_001_workspaces` — the table, `wkm_002_workspaces_list_index` — the index, `wkm_003_description_len` — `description` narrowed to 128, `wkm_004_sort` — the position and the index rebuilt for it |

The list order is a task group's: higher `sort` on top, then title, then code. A workspace
created without a number lands at the end of the list; the form sets the number directly.

One table — `workspaces`, without the module-name prefix: the module and the entity are one and
the same here, and `workspace_workspace` would be a stutter. The prefix answers "whose is this"
where there is more than one entity (`tasks_area`, `tasks_task`); here the name itself answers it.

The first two revisions are split apart, and the split is not a matter of taste. The table is the
target of a cross-module FK, and `depends_on` may only point at a non-head, so the creating
revision is buried under the next one: `wkm_001_workspaces` creates the table,
`wkm_002_workspaces_list_index` adds the list index. The technique is explained in
`conventions/db-migrations.md`.

The database holds the bare hex code. The `WORKSPACE@` type word is added at the boundary and
stripped on input (`codes.py`); a code with a foreign prefix is a mixed-up argument, not a
missing row, and the API answers it with 400, not 404.

There are two deletions, each with its own URL. The soft one sets a mark and leaves the contents
in place. `purge` removes the row, and the FK cascade takes with it everything the modules above
kept in this workspace. Hiding the irreversible behind a flag on the reversible would separate
them by one character in the URL.

## Contents

| File | What it holds |
| --- | --- |
| `module.py` | The module declaration: name, migrations directory, the `internal` zone router at `/workspace` |
| `api.py` | HTTP: list, create, read, update, soft delete, `restore`, `purge` |
| `stats.py` | The counter registry — the hook the modules above attach to |
| `models/workspace.py` | The ORM row of the `workspaces` table |
| `crud/workspace.py` | Store access; truncates long text rather than rejecting it — except the description, which is refused over 128 |
| `dto.py` | Response contracts: `WorkspaceRow`, `WorkspaceListRow`, `WorkspaceCounterRow` |
| `codes.py` | Code generation and the `WORKSPACE@` boundary prefix |
| `constants.py` | Code length and column widths — one source for the model, the migration and the CRUD |
| `text.py` | `clip` — the soft length limit at the entrance to the store; `fit` — the hard one, for the description |
