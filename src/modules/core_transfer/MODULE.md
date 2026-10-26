# core_transfer

Version: `1.0.0`

The module is what every export and import of an entity between installations has in common. A
consumer — `tasks` for a task (`.utsk`), `codex` for a codex (`.ucdx`) — declares its archive and
gets the container that writes and reads it, the references rewritten by a map, the shape of a
conflict of codes and the check of a person's choices, the files taken into the storage under the
codes they had, and a place on disk for an upload waiting for its import.

No tables, no migrations, no routes. It imports `src/core` and `core_storage` only.

## Responsibility

| Part | Where | What it does |
| --- | --- | --- |
| container | `container.py` — `ArchiveFormat`, `ArchiveWriter`, `ArchiveReader` | a zip whose first entry `mimetype` is stored uncompressed; entries named by the consumer's patterns; the manifest written last with the size and sha256 of every entry. Reading is a ladder: the container, the names, the unpacking limit, the manifest, then every byte against it |
| manifest | `manifest.py` | format, version (a newer one is refused), archive id, source installation, root entity, counts, inventory, references out of the archive |
| rows | `rows.py` | an ORM row ↔ a JSON object by the model's columns; timestamps in the API format; values cut to their columns |
| references | `refs.py` — `ReferenceScheme` | collects `TYPE@CODE` in a text and rewrites them by `(type, old code) → new code` in one pass; aliases (`IMAGE` → `FILE`) |
| conflicts | `conflicts.py` | a conflict with its options, the reason an option is missing, the choice it requires of another one, the dates of both sides; `resolve_choices` refuses a conflict left without a valid choice; `plan_token` fingerprints what the person saw |
| files | `files.py` | judges each archived file by «code + sha256» — `create` under its code, `reuse` / `recode` (the same content is not a conflict), `conflict` (the code holds other bytes); `take_file` stores or attaches it for an owner; `release_taken` gives owners back |
| uploads | `uploads.py` — `UploadArea` | `tmp/transfer/<consumer>/import` for an upload under its ULID with the browser's name beside it, `…/export` for an archive being sent; anything a day old is swept by the next upload |
| installation | `install.py` | the id of this installation, to tell its own archive from another's |
| refusals | `errors.py` — `TransferError` | codes without a module segment (`transfer_not_archive`, …): one wording for every consumer, in the interface's shared dictionary |

## Rules for a consumer

- Take every file before writing a row: `take_file` opens the storage's own transaction and must
  not run inside the consumer's `write_scope`. Rows failed — `release_taken` the owners.
- Build the plan anew for the apply and compare `plan_token`: the base may have changed while the
  person was choosing.
- Keep the group-like layout of one installation (a task's group, a codex's mounts) out of the
  archive; the import asks for it instead.

## Errors

| Code | When |
| --- | --- |
| `transfer_not_archive` | not a zip, or not this format's `mimetype` first |
| `transfer_foreign_format` | another kind of archive |
| `transfer_newer_format` | a newer format version |
| `transfer_manifest_invalid` | no manifest, or an unreadable one |
| `transfer_entry_not_allowed` | an entry the format never writes |
| `transfer_inventory_mismatch` | entries differ from the manifest |
| `transfer_entry_damaged` | an entry's size or sha256 differs |
| `transfer_archive_too_large` | over a limit (upload 1 GiB, unpacked 4 GiB, text entry 64 MiB) |
| `transfer_archive_inconsistent` | a row points outside the archive or breaks its kind's rules |
| `transfer_file_too_large` | a file over this installation's storage ceiling |
| `transfer_upload_not_found` | an unknown or removed upload |
| `transfer_plan_changed` | the conflicts are not the ones the person chose for |
| `transfer_decision_invalid` | a conflict without a valid choice |
