# core_storage

Version: `2.6.0`

The module registers files and keeps their bytes. A consumer hands over a file in any form — bytes,
a stream, a path on disk — and gets back a code; the module puts the bytes into one of its stores,
keeps one content once per store, counts who holds the file and removes it after a configured term
once nobody does. For each owner it keeps the name the file came in under.

## Responsibility

| Operation | Function | What it does |
| --- | --- | --- |
| register | `file_register_bytes`, `file_register_stream`, `file_register_path` | takes the file into a store with its first owner and that owner's name of it; the same bytes in the same store come back as the existing file, and the new owner's row gets its own name. `file_register_path(move=True)` hands the file to the module: moved into place without a copy, or deleted when the content is already stored; a path inside the storage root is refused with `move` |
| spool | `file_spool`, `file_register_spooled` | an async context: writes a stream to a temporary file under the size ceiling and yields it as a `SpooledFile` — path, sha256, size, first bytes — removed on leaving unless a registration moved it; for a consumer that must hold nothing (a lock of its own) while a slow upload arrives, then registers with `file_register_spooled`, which takes the counts and does not read the bytes again (only a file in the module's own `tmp` is taken) |
| take | `file_attach` | adds an owner to a stored file; revives a soft-deleted one. `filename` names the file in that place; without it a new owner takes the earliest name the file has |
| release | `file_release` | releases one place of one owner; the last live owner leaving marks the file deleted. `False` — the owner held no live place under that key, nothing changed |
| release an entity | `owner_release_everywhere` | releases an entity from every file and place it held |
| live places of a type | `held_by_type` | every live place of one owner type as `HeldFile(file_code, owner)` — for a consumer reconciling its bindings with what the storage counts; `taken_before` keeps only the places that took their file before that moment |
| owners | `file_owners` | who holds a file, each as a `FileOwner`: the `Owner`, its original name and extension, when it took the file (a revived place — when it was revived) and when it released it |
| get | `file_get`, `file_get_many`, `file_path`, `file_open` | the file's data, its path, its bytes; a soft-deleted file only with `include_deleted=True` |
| find by content | `file_find_content` | the file holding these bytes (by sha256) in a store, a soft-deleted one too — read only: what a registration of that content would answer with |
| delete | `file_delete` | the file manager's soft deletion of a file and all its owners |
| clean up | `purge_expired`, `purge_temporaries`, task `core_storage.cleanup` | removes files marked longer than the term, with their bytes and the code folders they leave empty; a file an owner takes back during the run is kept, the run goes on. The same task removes temporary files untouched for an hour — the module's spools `tmp/core_storage-*.part`, the cross-device copies `.<CODE><ext>.<hex>.part` inside the stores, and a consumer's own (`register_temporaries(folder, prefix)`) |
| reconcile | `reconcile_storage`, task `core_storage.reconcile`, `app.py storage check [--fix] [--sha]` | the base against the disk, past a grace of an hour: a held file whose bytes are gone is reported and logged, never removed — the same content uploaded again brings its bytes back; a marked one is left to the cleanup; bytes of another size (or sha256, with `--sha`) are reported; bytes no row points at are removed under the file's row lock. The hourly task removes them only when they are few and the root is not likely another base's; the command only reports unless `--fix` |
| serialise a holder | `holder_lock`, `holder_locks` | one file operation of one owner entity at a time inside the process — for a consumer whose binding rows and owner rows are written in separate transactions |

Every transaction that changes a file's owners or its mark — take, release, release an entity,
the file manager's deletion, a registration joining stored bytes, the cleanup of one file — takes
the file's row first (`SELECT … FOR UPDATE`; SQLite renders none and runs one writer at a time
with `BEGIN IMMEDIATE`). On PostgreSQL the writers of one file queue there, so "a live owner is
left" and "the file is not marked" stay one fact: two last owners leaving at once mark the file, a
release racing an attach never leaves a held file marked. A registration that waited for a row the
cleanup removed finds no row and stores the bytes as a new file.

The holder lock does not reach another process. Where `src/app.py` runs more than one (a separate
`--worker`, `SERVER_PROCESSES > 1`), a consumer's reconciliation stays safe by age: it asks
`held_by_type(…, taken_before=now − grace)` and releases only those, and an attach in flight —
its owner taken, its binding not yet written — is never minutes old. Reviving a released row
writes `created_at` anew for the same reason.

A code is taken in any case. A malformed code is `FileNotFound`, the same as a code nobody
registered: `file_get_many` leaves it out, `file_owners` answers that nobody holds it.

A code is random, unless the registration names one: `preferred_code` of `file_register_path` and
`file_register_spooled` is the first code tried — for a file coming back from another installation
under the code its texts quote. Taken or malformed, the random tries follow as usual; the dedup
comes first, so the same content answers with the code it has here. Read `StoredFile.code`.

An owner is the consumer's triple: `owner_type` + `owner_id` name its entity, `owner_key` the place
inside it (`''` — the whole entity). The module does not read it, but checks it on construction:
non-empty type and id, strings, none wider than its column — SQLite would store a longer value,
PostgreSQL would refuse it.

## Original name

The name an owner brings — `filename` for bytes and a stream, the source's name or `filename` for
a path — is kept on that owner's row split before its last suffix, case kept:
`report.final.PDF` → `original_filename` `report.final` + `original_extension` `.PDF`. The two
put together give the name back exactly as it came in. No suffix, a dotfile (`.env`) or a suffix
wider than 16 characters — the name stays whole and the extension is `''`. No name at all — both
are `''`. Over 255 characters without the extension, or a control character anywhere in it
(U+0000–U+001F, U+007F: a name is one line, and PostgreSQL cannot store U+0000), is a `ValueError`
before anything is written.

The name serves showing the file and handing it out; it decides nothing. The type comes from the
bytes first, and the stored `extension` — the one on disk — from the found mime, lower case.

When a name is written to an owner row:

| The owner's row | Registration with a name | Registration without one | `file_attach(filename=…)` | `file_attach()` |
| --- | --- | --- | --- | --- |
| none yet | the brought name | `''` | the given name | the earliest name the file has, else `''` |
| released (also by the file manager's deletion) | the brought name, row revived | the row's name, row revived | the given name, row revived | the row's name, row revived |
| live | **the row's name** | the row's name | the given name | the row's name |

A registration never renames a live place: a consumer holding the file refuses the second
registration, and a refusal must leave the place as it was. Renaming a live place is an explicit
`file_attach` with `filename`.

"The earliest name the file has" is the owner row with the smallest `created_at`; the column keeps
whole seconds, and rows taken in one second go by the owner triple in plain order (`owner_type`,
`owner_id`, `owner_key`). It looks at every owner: the module knows no boundary between them.
One content brought by two consumers' entities is one file, so a consumer that keeps its owners
apart — a workspace must not see a name brought in another — passes `filename` itself.

## Settings

| Key | Default | Meaning |
| --- | --- | --- |
| `cleanup_after_hours` | 48 | how long a file nobody holds waits for removal |
| `cleanup_limit` | 0 | files per cleanup run; 0 — no limit |
| `max_file_size_mb` | 128 | the size ceiling |

## Stores

The store list comes from the constructor — `CoreStorageModule(stores=["public", "private"])` in
`build_modules`. A store is a folder inside the storage root — `STORAGE_PATH` of the core config
(`Config.storage_root`), by default `runtime/<APP_ENV>/storage` (`AppPath.storage`); the temporary
directory is `AppPath.tmp`. The bytes belong to the database that counts their owners: a database
file outside `runtime/<APP_ENV>/` with no `STORAGE_PATH` is warned about at `configure` — a copy
sharing the original's stores would have its cleanup remove the original's files, and its
hourly reconciliation removes nothing on such a root. What a store means — who may read its files — is not the module's
knowledge. A store taken off the list closes to new files; its stored files stay readable.

## Boundaries: what is not here

No metadata beyond the original name: description, source identity (URL, source path, payload
hash), role and order are the consumer's to keep. No binding to the consumer's entities beyond the
opaque owner triple. No HTTP router, no MCP, no serving of files,
no content checks: those are other layers. The boundary has been crossed if this module imports an
application module or mentions an entity of one.
