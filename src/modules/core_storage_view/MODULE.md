# core_storage_view

Version: `2.1.0`

The module is the HTTP face of `core_storage` for reading. It serves the files of the `public`
store by code in the core zone `/storage` — opened in a tab or saved under the name the address
gives. `core_storage` itself keeps no routes; taking a file in — the person's upload, the agent's
file by path or at an upload address — is `core_storage_upload`.

`2.0.0` reads no holder: the name to save under rides in the address (`/download/<name>`), and
`?download=1` and `?holder=` are gone along with the holder registry. `2.1.0`: a name without an
extension takes the file's own.

## Responsibility

| Operation | Where | What it does |
| --- | --- | --- |
| open | `GET`/`HEAD /storage/{store}/{code}` | the bytes of a file of `public` with its stored mime, to open in the tab |
| download | `GET`/`HEAD /storage/{store}/{code}/download` | the same bytes, saved under `<CODE><extension>` |
| download under a name | `GET`/`HEAD /storage/{store}/{code}/download/{name}` | saved under `name`; a name without an extension takes the file's |
| refuse | every route | any miss — a store that is not served, an unknown or malformed code, a soft-deleted file, a row without bytes — is one 404 `File not found`, the same body for every code |
| link | `public_file_path(code)`, `public_download_path(code, name="")`, `app_url(path)` | `/storage/public/<CODE>`, `…/download[/<name>]` with the name percent-encoded, and a path made absolute on the server's own host and port |

## Headers of a served file

| Header | Value |
| --- | --- |
| `Content-Type` | the stored mime (`text/*` gets `; charset=utf-8` from Starlette) |
| `X-Content-Type-Options` | `nosniff`, always |
| `Content-Security-Policy` | `sandbox` for `text/html`, `application/xhtml+xml`, `application/xml`, `text/xml`, `image/svg+xml` and any `*+xml` |
| `Content-Disposition` | `inline` (open) or `attachment` (download); `filename="<ascii>"; filename*=UTF-8''<percent-encoded>` (RFC 6266 / 5987) |
| `ETag` | `"<sha256>"`; a matching `If-None-Match` gets 304 without the bytes |
| `Cache-Control` | `no-cache` |
| `Accept-Ranges` | `bytes` (Starlette serves ranges) |

The files come from the app's own origin: without the sandbox, a script in an uploaded SVG or HTML
would run with the app's rights. PDF is not sandboxed — a sandboxed PDF does not open in Chrome's
viewer.

The name is the address's. Whoever hands a link out — the agent surface, the page — knows what the
file is called where it is shown and puts that name in the path; the route reads no holder and no
workspace, so a name given in one workspace never goes out by itself. The name only says what to
save the bytes as: the bytes and their type are the stored ones, whatever the name's extension. A
name with no extension — usually a title a holder gave the file — takes the stored one: the sender
of the link knows the title, not the extension, and a file saved without one opens with nothing. A
name the storage could not keep as a file's name (a control character, too long) and an opening
without a name go out under `<CODE><extension>`. The ASCII `filename` is the name itself when it
is printable ASCII without `"`, `\` or `%`, else `<CODE><extension>`.

Caching: the bytes under a code never change, but a soft-deleted file must stop being served at
once. `no-cache` with the sha256 tag makes the browser ask every time and costs a 304 when nothing
changed; a long `max-age` would keep a deleted file in the browser's cache.

## Boundaries: what is not here

No intake of any kind — the person's upload, the agent's file, the upload address are
`core_storage_upload`'s. No binding of a file to an entity, no MCP tools or resources — those are
the consumers' and the agent surface's. No store other than `public` is served. No tables,
migrations or settings. The module imports only `src/core` and `core_storage` (`services`, `dto`,
`errors`, `names`). The boundary has been crossed if it imports an application module, the upload
module, or mentions an entity of one.
