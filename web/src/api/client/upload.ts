// Sending a file as the body of a request, with the progress of the sending.
//
// `fetch` reports no upload progress, so this one transport is an XHR — under the same rules as
// the JSON client (`createClient.ts`): zone-relative paths only, the zone's headers (the tab id
// the change feed recognises its own edits by), the same error envelope as an `ApiError`, a
// redirect taken for a broken contract. The body is the file as is, one file per request; what
// else the route needs (the name, a place) rides in the query.
//
// No timeout: a large file over a slow link takes as long as it takes, and the person sees it
// moving. Cancelling is the caller's — `signal`.
import { ApiError, apiErrorFromText } from './createClient'

type QueryValue = string | number | boolean | null | undefined

export interface UploadOptions {
  query?: Record<string, QueryValue>
  /** Bytes sent so far out of the total, as the browser reports them. */
  onProgress?: (loaded: number, total: number) => void
  signal?: AbortSignal
}

export interface UploaderConfig {
  /** Zone path prefix, e.g. '/internal'. */
  prefix: string
  /** Backend origin for direct-HTTP dev (VITE_API_BASE); '' for same-origin. */
  origin?: string
  headers?: Record<string, string>
}

export type Uploader = <T>(path: string, file: Blob, opts?: UploadOptions) => Promise<T>

export function createUploader(config: UploaderConfig): Uploader {
  const ORIGIN = config.origin ?? ''

  function buildUrl(path: string, query?: UploadOptions['query']): string {
    if (/^https?:\/\//i.test(path))
      throw new Error(`upload: absolute URLs are not allowed ('${path}')`)
    const url = ORIGIN + config.prefix + path
    const qs = new URLSearchParams()
    for (const [k, v] of Object.entries(query ?? {}))
      if (v !== null && v !== undefined) qs.append(k, String(v))
    const s = qs.toString()
    return s ? `${url}?${s}` : url
  }

  return <T>(path: string, file: Blob, opts: UploadOptions = {}) =>
    new Promise<T>((resolve, reject) => {
      const xhr = new XMLHttpRequest()
      xhr.open('POST', buildUrl(path, opts.query))
      xhr.withCredentials = Boolean(ORIGIN)
      for (const [name, value] of Object.entries(config.headers ?? {})) xhr.setRequestHeader(name, value)
      xhr.setRequestHeader('Accept', 'application/json')
      xhr.setRequestHeader('Content-Type', file.type || 'application/octet-stream')

      if (opts.onProgress) {
        const report = opts.onProgress
        xhr.upload.addEventListener('progress', (event) => {
          report(event.loaded, event.lengthComputable ? event.total : file.size)
        })
      }

      const abort = () => xhr.abort()
      opts.signal?.addEventListener('abort', abort, { once: true })
      const done = () => opts.signal?.removeEventListener('abort', abort)

      xhr.addEventListener('load', () => {
        done()
        // XHR follows redirects itself; an answer from another address is not our API.
        if (xhr.responseURL && !xhr.responseURL.includes(config.prefix + path)) {
          reject(new ApiError(0, { error: 'API contract violated: the upload was redirected', code: 'protocol' }))
          return
        }
        if (xhr.status < 200 || xhr.status >= 300) {
          reject(apiErrorFromText(xhr.status, xhr.statusText, xhr.responseText, xhr.getResponseHeader('retry-after')))
          return
        }
        if (!xhr.responseText) {
          resolve(undefined as T)
          return
        }
        try {
          resolve(JSON.parse(xhr.responseText) as T)
        } catch {
          reject(new ApiError(xhr.status, { error: 'API contract violated: the response body is malformed JSON', code: 'protocol' }))
        }
      })
      xhr.addEventListener('error', () => {
        done()
        reject(new ApiError(0, { error: 'Network error', code: 'network' }))
      })
      xhr.addEventListener('abort', () => {
        done()
        reject(new ApiError(0, { error: 'Request aborted', code: 'aborted' }))
      })

      if (opts.signal?.aborted) {
        xhr.abort()
        return
      }
      xhr.send(file)
    })
}
