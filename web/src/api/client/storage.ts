// Client for the STORAGE zone (`/storage/*`) — the files: served at `/storage/public/<CODE>` by
// plain links, taken in at `/storage/upload` by `storageUpload`. The same rules as the internal
// zone's uploader (`internal.ts`): zone-relative paths, the tab tag the change feed recognises our
// own edits by. The browser adds `Origin` to the request itself — that is what lets the person's
// page write there (`core_storage_upload`).
import { CLIENT_ID, CLIENT_ID_HEADER } from './client-id'
import { createUploader } from './upload'

export { ApiError } from './createClient'
export type { UploadOptions } from './upload'

// A file sent as a request body, with progress. It reports nothing by itself: an upload's refusal
// belongs next to the file it is about, and the caller shows it there.
export const storageUpload = createUploader({
  prefix: '/storage',
  origin: import.meta.env.VITE_API_BASE ?? '',
  headers: { [CLIENT_ID_HEADER]: CLIENT_ID },
})
