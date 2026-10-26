# core_storage_upload

Version: `1.0.0`

The module takes files in as they are, from the person and from the agent, and hands each to the
holder its code names. It is the intake side of `core_storage`: the storage registers and keeps the
bytes, `core_storage_view` serves them, this module takes them. In the interface it is called
«Загрузка файлов» / «File upload».

## Responsibility

| Operation | Where | What it does |
| --- | --- | --- |
| holders | `register_upload_holder(prefix, UploadHolder(check, attach, answer))` | a consumer tells how `<PREFIX>@<bare>` takes a file: `check(bare, payload, workspace)` before the body, `attach(bare, spooled, payload, filename, workspace)` under its own lock, `answer` — the file as its list shows it |
| the person's upload | `POST /storage/upload?holder=&filename=&title=&description=` | the body is the file; from the app's own page only; the payload is `{title, description}`; 201 with the holder's `answer` |
| an upload request | `open_upload_request(holder, *, workspace, payload, filename_hint, ttl=None)` | asks the holder with the agent's workspace, writes a row of `core_storage_upload_request`, returns `UploadAddress(path, url, expires_at)` |
| the upload of a request | `PUT /storage/upload?token=…[&filename=]` (POST too) | finds the open request by its token, asks the holder again with the stored workspace, binds with the stored payload, deletes the request; 200 with the opener's answer (`register_upload_answer`) |
| a path on the server | `server_file(path)`, `take_server_file(holder, source, *, payload, workspace)` | what the server finds at the path; the file read into a spool and handed to the holder, left where it is |
| the cleanup | `RequestCleanupTask` (`core_storage_upload.cleanup`, `10 * * * *`, TTL 600) | deletes the expired requests (`purge_expired_requests`) |

The **payload** is what the client asked the holder for — a title and a description for the
holders there are. The module carries it from the query or the request row to the holder and never
reads it; the name of the file is not in it — that one is the module's to check.

## Who may write

The upload address is one, `/storage/upload`, and a request is let in as one of two clients before
a byte of the body is read:

- **the person's page** — no `token`, `Origin` present and allowed (`origin_allowed` of the core:
  the backend's own origin or a dev origin of `Config.cors_origins`);
- **a client with an open upload request** — `?token=…`.

Neither — no `Origin` and no token, which is what `curl` or a script on the machine sends — is
401 `core_storage_upload.request.unauthorized`. A foreign `Origin` without a token is 403
`origin_refused`. The core's `same_origin_only` is not used here: it lets a request without
`Origin` through.

## The upload request

- **What is kept** (`core_storage_upload_request`, chain `csu_*`): the sha256 of the token as the
  key, the holder's code, the workspace's code, the name hint, the payload (JSON — `JSONB` on
  PostgreSQL), `claimed_at`, `expires_at`, `created_at`. The token itself — 32 bytes of a CSPRNG,
  url-safe — is never stored and travels only in the address. No data of the request rides in the
  address.
- **Opening** asks the holder with the workspace (a task of it, a codex note its mount lets the
  agent write), checks the name hint, writes the row and nothing else: no binding until the bytes
  come. The lifetime is the setting `request_ttl_minutes` at the moment of opening.
- **The bytes**: the open request (not expired, no upload in flight) — else 404
  `core_storage_upload.request.not_found`, one answer for an unknown, expired, used or busy token;
  a `holder` the PUT names other than the request's — 400 `.request.foreign_holder`; the name
  (`?filename=` replaces the hint); the holder asked again with the stored workspace — a task may
  be deleted, a mount may have lost the agent's right; the declared size — all before the body.
- **Once.** The request is claimed by one statement (`UPDATE … SET claimed_at WHERE claimed_at IS
  NULL AND expires_at > now`): on PostgreSQL the row lock queues concurrent claims, on SQLite the
  writers are one at a time. Of two PUTs at once exactly one binds; the other gets the 404. After
  the binding the row is deleted.
- **A failure gives the request back**: over the ceiling, a body that breaks off, the holder
  refusing — `claimed_at` is cleared and the client tries again until the request expires. A
  process dying mid-upload leaves the request claimed until it expires.
- **Bytes the holder has already** (`AlreadyHeld`) complete the request with that file.
- **The answer** is in the words of whoever opens the requests: `register_upload_answer(answer)`;
  without one — the file's bare code, title and description.
- **It outlives a restart** and is taken by any server process: nothing is held in memory.
- **The access log**: the token rides in the address, and `configure` puts a filter on
  `uvicorn.access` that blanks `token=` in the lines of this route (`access_log.py`).

## Refusals

| Status | Code | When |
| --- | --- | --- |
| 400 | `core_storage_upload.holder.unknown` | no holder registered the prefix, or the code is empty; `params.holder` |
| 400 | `core_storage_upload.filename.control_character` | a control character anywhere in the name sent |
| 400 | `core_storage_upload.filename.too_long` | more than the storage keeps as the original name |
| 400 | `core_storage_upload.request.foreign_holder` | the PUT names another holder than its request's |
| 401 | `core_storage_upload.request.unauthorized` | no `Origin` and no token |
| 403 | `origin_refused` | a page of another site |
| 404 | `core_storage_upload.request.not_found` | no open request under the token |
| 413 | `core_storage_upload.file.too_large` | over `core_storage`'s `max_file_size_mb`, by `Content-Length` before the body or while it streams; `params.limit` in bytes and `limit_mb` |
| 404 / 409 / 403 / 400 | the holder's | `HolderRefused` of kind `MISSING` / `CONFLICT` / `FORBIDDEN` / `INVALID`, with the holder's code and `params`; the same bytes again on the person's page — 409 with the file in `params` |

The texts of the codes and of the cleanup job are in `web/src/features/core_storage_upload/locales`.

## Settings

| Key | Default | Meaning |
| --- | --- | --- |
| `request_ttl_minutes` | 15 (1…1440) | how long an upload request stays open |
| `server_path_enabled` | `true` | whether a path on the server's disk is read; off — every path is `None`, the client sends the bytes |

They change without a restart: `on_settings_change` hands the store over, every reader asks at the
moment of use. There is no ceiling of the module's own: the storage's `max_file_size_mb` is the
one ceiling.

## A path on the server

`server_file(path)` — the readable file the path names, or `None` when the server cannot see one
(relative, absent, behind a folder it may not enter, the home of an unknown user) or reads no path
at all. `ServersOwnFile(reason)` for the kernel's `/proc`, `/sys`, `/dev`, the installation's
`runtime/`, its `.env*`, and its SQLite file (with `-wal`/`-shm`), copies and stores wherever
`DB_PATH` / `STORAGE_PATH` put them — links followed first; `NotAFile`; `UnreadableFile(reason)`.
The refusals are not worded for a reader: the caller knows who asked. `take_server_file` refuses
the name and asks the holder before it opens; the opened file is checked again — the path
resolved anew, the guard asked, the file at its end the very one opened — since a link may be
turned elsewhere after `server_file` found it; then its size on disk; the file is read into a spool with
no lock held and stays where it was.

## Boundaries: what is not here

No binding of a file to an entity and no holder's rule — the consumers' (`tasks`, `codex`
register their holders in `configure`); no serving — `core_storage_view`; no agent surface — `workbench` calls the services and words
the answers. The module imports only `src/core` and `core_storage` (`services`, `dto`, `errors`,
`settings.max_file_size`, `names.split_filename`); the boundary has been crossed if it imports an
application module or mentions an entity of one.

## Package

```
src/modules/core_storage_upload/
  module.py        class, version, configure: the access log filter, the cleanup job
  MODULE.md        this description
  constants.py     the route, the token's size, column widths, the settings' defaults
  settings.py      request_ttl_minutes, server_path_enabled
  errors.py        refusals and their codes
  dto.py           Payload, AttachedFile, UploadHolder, UploadRequest, UploadAddress
  api.py           POST|PUT /storage/upload
  access_log.py    the token out of uvicorn's access log
  models/          core_storage_upload_request
  crud/            open, claim, give back, delete, purge
  services/        holders, intake, requests, server_path — the public layer
  tasks/           RequestCleanupTask
  migrations/versions/csu_001_request.py
```
