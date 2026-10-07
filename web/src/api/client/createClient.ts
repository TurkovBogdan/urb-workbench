// Factory for a same-origin JSON client — the shared machinery behind every zone client
// (today only the internal API, `/internal`). A zone differs by config alone: its path
// PREFIX and its policy callbacks. Everything else is identical and lives here once:
//
//  - Calls go only to our own origin via relative paths; credentials default to
//    'same-origin'. Absolute URLs are rejected outright.
//  - Errors follow the backend envelope (`src/core/api/errors.py`): { error, code?, fields? }.
//    Every non-2xx is thrown as a typed `ApiError`. Network/abort/timeout normalize too.
//  - The response must be JSON. A redirect is NOT a response: `redirect: 'manual'` — it is never
//    followed (it has to be forbidden up front: after the response the request has already gone
//    to a foreign address); a non-JSON body and unparseable JSON are rejected too. All of these
//    are an `ApiError` with code `protocol`.
//  - Every request has a timeout: otherwise a hung backend silently hangs the app.
//  - A failure the screen did not show itself is reported via `onError` (see `shouldReport`).
//
// The session layer (CSRF, 401/403, "session lost") was carried over from the donor portal whole,
// but the internal zone has no auth, so it is switched off by config: `csrf: false` and no
// `loginPath`/`onUnauthenticated`. Enabling CSRF without the matching middleware on the backend
// would add a failing GET `<prefix>/csrf-cookie` before EVERY write.
//
// Dev mode: set VITE_API_BASE to the ORIGIN of a backend reachable directly (no Vite proxy),
// e.g. http://localhost:22040. When set, requests go absolute + credentials: 'include'. Empty
// (default, and always in prod where the SPA is same-origin) keeps the strict same-origin path.

export interface ClientConfig {
  /** Zone path prefix prepended to every call, e.g. '/internal'. */
  prefix: string
  /** Backend origin for direct-HTTP dev (VITE_API_BASE); '' for same-origin (prod default). */
  origin?: string
  /** Headers sent with every request of the zone (e.g. the tab id — `client-id.ts`). */
  headers?: Record<string, string>
  /**
   * Double-submit CSRF token on writes: cookie `XSRF-TOKEN` → header `X-XSRF-TOKEN`, cookie
   * refresh via `<prefix>/csrf-cookie` and one silent retry on 419. Enable only for a zone whose
   * backend actually has this check.
   */
  csrf?: boolean
  /** Where a 401 sends the browser (the zone's login address). No login — leave unset. */
  loginPath?: string
  /** Show a permission denial: a shell screen at the current address, no navigation. */
  onForbidden?: () => void
  /**
   * The session has ended (401). An app that can route to login ON ITS OWN sets the callback and
   * gets a transition inside the SPA; without it the client reloads the page at `loginPath`,
   * losing unsaved input. The argument is the address where the person was caught.
   */
  onUnauthenticated?: (returnTo: string) => void
  /**
   * The opposite: the session is ALREADY open (409 `already_authenticated` from a guest endpoint).
   * The app adopts it and routes to the dashboard; the login form need not know about this case.
   */
  onAlreadyAuthenticated?: () => void
  /**
   * Show a failure to the person. The client decides WHAT to report (see `shouldReport`), the
   * app decides HOW: usually as a toast. Without the callback the failure stays mute.
   */
  onError?: (error: ApiError) => void
  /**
   * Whether the app knows the session is gone. While it is, requests to protected endpoints don't
   * hit the network at all: a person who got logged out keeps clicking, and otherwise every click
   * spends the zone's shared rate limit, coming back as 429 instead of an honest "log in again".
   */
  isSessionLost?: () => boolean
  /** Response timeout, ms. Defaults to REQUEST_TIMEOUT_MS. */
  timeoutMs?: number
}

/** Timeout for a single request. We have no live endpoints that take longer. */
const REQUEST_TIMEOUT_MS = 20_000

/**
 * Failure codes set by the client ITSELF (for the rest the code comes from the backend).
 * `protocol` — the response is not our JSON: a redirect, a foreign content-type, a broken body.
 */
export type ClientErrorCode = 'network' | 'timeout' | 'aborted' | 'protocol' | 'session_lost'

/** Machine code of the 409 "you are already logged in" — read by the auth layer, not a person. */
export const ALREADY_AUTHENTICATED = 'already_authenticated'

// Mirror of backend ErrorBody (src/core/api/errors.py). `fields` — per-form-field errors;
// `code` carries the backend's machine code or one of ClientErrorCode; `params` — values to
// interpolate into the code's text; `error` — English fallback text (see `api/errorText.ts`).
export interface ApiErrorBody {
  error: string
  code?: string
  params?: Record<string, string | number>
  fields?: Record<string, string>
  /** Seconds from the `Retry-After` header of a 429 — how long to actually wait. */
  retryAfter?: number
}

// Thrown for every non-2xx response. `status` 0 + code 'network' = transport failure.
export class ApiError extends Error {
  readonly status: number
  readonly code?: string
  readonly params?: Record<string, string | number>
  readonly fields?: Record<string, string>
  readonly retryAfter?: number

  constructor(status: number, body: ApiErrorBody) {
    super(body.error)
    this.name = 'ApiError'
    this.status = status
    this.code = body.code ?? undefined
    this.params = body.params ?? undefined
    this.fields = body.fields ?? undefined
    this.retryAfter = body.retryAfter
  }
}

/**
 * Whether to report a failure to the person. One rule for all requests:
 * 422 is the form's business (fields are there), 401/403/409 are a state change handled by the
 * auth layer and the shell, a cancel by the caller and an already known session loss are not news.
 * Everything else pops up unless the caller said `report: false`, because then it is obliged to
 * show it itself.
 */
function shouldReport(error: ApiError, opts: RequestOptions): boolean {
  if (opts.report === false) {
    return false
  }

  if (error.status === 401 || error.status === 403 || error.status === 422) {
    return false
  }

  // 404 means "nothing to see at this address", and the section shows that as a state in its own
  // place (`SectionError`). A toast on top would duplicate the same news a second way.
  if (error.status === 404) {
    return false
  }

  // ⚠️ Stay silent about only ONE 409 — "you are already logged in", handled by the auth layer.
  // Other 409s are domain ones, and muting them means losing the failure.
  if (error.status === 409 && error.code === ALREADY_AUTHENTICATED) {
    return false
  }

  return error.code !== 'aborted' && error.code !== 'session_lost'
}

type QueryValue = string | number | boolean | null | undefined

export interface RequestOptions {
  query?: Record<string, QueryValue>
  // 401 policy: 'redirect' (default) bounces to the zone login; 'throw' lets the caller handle
  // it (auth bootstrap / login form).
  on401?: 'redirect' | 'throw'
  // 403 policy: 'redirect' (default) hands the refusal to the shell; 'throw' lets the caller
  // handle it inline.
  on403?: 'redirect' | 'throw'
  /** `false` — the caller shows the failure itself; by default the client shows it. */
  report?: boolean
  /** This request's own timeout, ms. Defaults to the zone-wide one. */
  timeoutMs?: number
  /** A login endpoint: works without a session, so the lost-session kill switch does not hold it. */
  allowGuest?: boolean
  signal?: AbortSignal
}

// Verbs returned by the factory. Paths are zone-relative (the prefix is prepended internally).
export interface ApiClient {
  get: <T>(path: string, opts?: RequestOptions) => Promise<T>
  post: <T>(path: string, body?: unknown, opts?: RequestOptions) => Promise<T>
  put: <T>(path: string, body?: unknown, opts?: RequestOptions) => Promise<T>
  patch: <T>(path: string, body?: unknown, opts?: RequestOptions) => Promise<T>
  del: <T>(path: string, body?: unknown, opts?: RequestOptions) => Promise<T>
}

// Read a cookie value (URL-decoded): the double-submit header must carry the decoded token.
function readCookie(name: string): string | null {
  const prefix = name + '='
  for (const part of document.cookie ? document.cookie.split('; ') : [])
    if (part.startsWith(prefix)) return decodeURIComponent(part.slice(prefix.length))
  return null
}

// One signal for "timeout expired" and "caller cancelled" — with a separate diagnosis: an abort by
// timeout and an abort at the will of outside code must land in different error codes. The
// ready-made AbortSignal.timeout/any pair can't tell them apart, hence our own controller.
function deadline(ms: number, external?: AbortSignal) {
  const controller = new AbortController()
  let expired = false

  const timer = setTimeout(() => {
    expired = true
    controller.abort()
  }, ms)

  const relay = () => controller.abort()
  if (external) {
    if (external.aborted) controller.abort()
    else external.addEventListener('abort', relay, { once: true })
  }

  return {
    signal: controller.signal,
    expired: () => expired,
    release: () => {
      clearTimeout(timer)
      external?.removeEventListener('abort', relay)
    },
  }
}

// A response arrived, but it is not our JSON. The body stays out of the message: it can be a
// whole html page.
function protocolError(status: number, what: string): ApiError {
  return new ApiError(status, { error: `API contract violated: ${what}`, code: 'protocol' })
}

// Map an error response to our normalized ApiError body.
async function toApiError(res: Response): Promise<ApiError> {
  const body: ApiErrorBody = { error: res.statusText || `HTTP ${res.status}` }

  // How long to wait before the next attempt is said by the server itself, not guessed by us.
  const retryAfter = Number.parseInt(res.headers.get('retry-after') ?? '', 10)
  if (Number.isFinite(retryAfter)) body.retryAfter = retryAfter

  // Read the body once, as a string: an empty response is fine (a failure may have no body), but a
  // NON-EMPTY non-JSON one means something other than our stack answered (a proxy page, a WAF
  // stub). Such a failure gets `protocol`, otherwise the person would see an English `statusText`
  // from a foreign node.
  const text = await res.text().catch(() => '')

  if (text !== '') {
    try {
      const data = JSON.parse(text)
      if (data && typeof data === 'object') {
        if (typeof data.error === 'string' && data.error) body.error = data.error
        if (typeof data.code === 'string') body.code = data.code
        if (data.params && typeof data.params === 'object') {
          const params: Record<string, string | number> = {}
          for (const [k, v] of Object.entries(data.params as Record<string, unknown>))
            params[k] = typeof v === 'number' ? v : String(v)
          body.params = params
        }
        if (data.fields && typeof data.fields === 'object') {
          const fields: Record<string, string> = {}
          for (const [k, v] of Object.entries(data.fields as Record<string, unknown>))
            fields[k] = Array.isArray(v) ? String(v[0]) : String(v)
          body.fields = fields
        }
      }
    } catch {
      body.code = 'protocol'
    }
  }

  return new ApiError(res.status, body)
}

/**
 * Build a JSON client bound to one zone. See ClientConfig / the file header.
 */
export function createClient(config: ClientConfig): ApiClient {
  const ORIGIN = config.origin ?? ''
  const PREFIX = config.prefix
  const CREDENTIALS: RequestCredentials = ORIGIN ? 'include' : 'same-origin'

  function buildUrl(path: string, query?: RequestOptions['query']): string {
    // Hard rule: zone-relative paths only — never let credentials reach another origin,
    // and keep the prefix owned here, not in callers.
    if (/^https?:\/\//i.test(path))
      throw new Error(`api client: absolute URLs are not allowed ('${path}')`)

    const url = ORIGIN + PREFIX + path
    if (!query) return url
    const qs = new URLSearchParams()
    for (const [k, v] of Object.entries(query))
      if (v !== null && v !== undefined) qs.append(k, String(v))
    const s = qs.toString()
    return s ? `${url}?${s}` : url
  }

  // Refresh the CSRF cookie. Under the same timeout as the request itself: otherwise a hung
  // `/csrf-cookie` blocks EVERY write indefinitely, and the same zone is responsible for it.
  async function refreshCsrfCookie(signal?: AbortSignal): Promise<void> {
    const clock = deadline(config.timeoutMs ?? REQUEST_TIMEOUT_MS, signal)

    try {
      await fetch(ORIGIN + PREFIX + '/csrf-cookie', { credentials: CREDENTIALS, signal: clock.signal })
    } catch {
      // ignore — the subsequent request will report the true failure
    } finally {
      clock.release()
    }
  }

  async function ensureCsrfCookie(): Promise<void> {
    if (readCookie('XSRF-TOKEN')) return

    await refreshCsrfCookie()
  }

  // The session is gone. An app with its own handler routes to login inside the SPA (input and the
  // bundle survive); a zone without login (`loginPath` unset) just passes the failure out.
  function handleUnauthenticated(): void {
    if (typeof window === 'undefined') return

    const to = window.location.pathname + window.location.search + window.location.hash

    if (config.onUnauthenticated) {
      config.onUnauthenticated(to)

      return
    }

    if (config.loginPath === undefined) return
    if (window.location.pathname === config.loginPath) return // already there — don't loop
    window.location.assign(`${config.loginPath}?return=${encodeURIComponent(to)}`)
  }

  // A failure going out: first report it (if the rule says it's ours to report), then throw. The
  // single exit point for errors from the client — otherwise "show" and "throw" drift apart across
  // callers.
  function raise(error: ApiError, opts: RequestOptions): never {
    if (config.onError && shouldReport(error, opts)) {
      config.onError(error)
    }

    throw error
  }

  async function request<T>(
    method: string,
    path: string,
    payload?: unknown,
    opts: RequestOptions = {},
    isRetry = false,
  ): Promise<T> {
    // Kill switch: there is no session and the app knows it — don't hit the network at all. Login
    // endpoints (`allowGuest`) are exempt, otherwise a logged-out person would have no way back in.
    if (opts.allowGuest !== true && config.isSessionLost?.() === true) {
      raise(new ApiError(0, { error: 'Session lost', code: 'session_lost' }), opts)
    }

    const write = method !== 'GET' && method !== 'HEAD'
    const csrf = config.csrf === true
    if (write && csrf) await ensureCsrfCookie()

    const headers: Record<string, string> = {
      ...config.headers,
      'Cache-Control': 'no-cache',
      Accept: 'application/json',
    }
    if (write && csrf) {
      const token = readCookie('XSRF-TOKEN')
      if (token) headers['X-XSRF-TOKEN'] = token
    }
    // `manual`: a redirect is NEVER followed. Otherwise the user agent replays POSTs as GET, and
    // the shell page arrives here as a successful response.
    const clock = deadline(opts.timeoutMs ?? config.timeoutMs ?? REQUEST_TIMEOUT_MS, opts.signal)
    const init: RequestInit = {
      method,
      credentials: CREDENTIALS,
      headers,
      redirect: 'manual',
      signal: clock.signal,
    }

    // Serialization happens INSIDE the timeout and inside normalization: a cycle or a BigInt in the
    // body is a code bug, but it must still come out as the same `ApiError`, not a raw TypeError.
    try {
      if (payload !== undefined) {
        headers['Content-Type'] = 'application/json'
        init.body = JSON.stringify(payload)
      }

      let res: Response
      try {
        res = await fetch(buildUrl(path, opts.query), init)
      } catch (e) {
        // The transport gave no response. Three different diagnoses that must not be mixed up: the
        // shell shows different screens for a timeout and a dropped network, and a cancel by the
        // caller must not be shown at all.
        if (clock.expired()) raise(new ApiError(0, { error: 'Request timed out', code: 'timeout' }), opts)
        if (opts.signal?.aborted) raise(new ApiError(0, { error: 'Request aborted', code: 'aborted' }), opts)
        raise(new ApiError(0, { error: (e as Error)?.message || 'Network error', code: 'network' }), opts)
      }

      // A redirect: the browser exposes neither body nor headers (status 0, type opaqueredirect) —
      // judge by the type.
      if (res.type === 'opaqueredirect') raise(protocolError(0, 'the API answered with a redirect'), opts)

      if (!res.ok) {
        // 419 = CSRF token expired/rotated. Refresh the cookie and retry the write once.
        if (res.status === 419 && write && csrf && !isRetry) {
          await refreshCsrfCookie(clock.signal)

          return request<T>(method, path, payload, opts, true)
        }

        const err = await toApiError(res)

        // Two statuses are not errors but a session state change, and they are handled here, in
        // one place: the caller only has to show its own step, not figure out where to route.
        if (err.status === 401 && opts.on401 !== 'throw') handleUnauthenticated()
        else if (err.status === 409 && err.code === ALREADY_AUTHENTICATED) config.onAlreadyAuthenticated?.()
        else if (err.status === 403 && opts.on403 !== 'throw') config.onForbidden?.()

        raise(err, opts)
      }

      // 204 / empty body → undefined; otherwise JSON and nothing else.
      if (res.status === 204) return undefined as T

      // ⚠️ Reading the body is under the timeout too: a server that sent headers and stalled on
      // the body would otherwise hang the promise forever — and on the first request that is an
      // eternal splash screen instead of the app.
      let text: string
      try {
        text = await res.text()
      } catch (e) {
        if (clock.expired()) raise(new ApiError(0, { error: 'Request timed out', code: 'timeout' }), opts)
        if (opts.signal?.aborted) raise(new ApiError(0, { error: 'Request aborted', code: 'aborted' }), opts)
        raise(new ApiError(0, { error: (e as Error)?.message || 'Network error', code: 'network' }), opts)
      }

      if (text === '') return undefined as T

      if (!(res.headers.get('content-type') ?? '').includes('application/json'))
        raise(protocolError(res.status, 'the response body is not JSON'), opts)

      try {
        return JSON.parse(text) as T
      } catch {
        raise(protocolError(res.status, 'the response body is malformed JSON'), opts)
      }
    } finally {
      clock.release()
    }
  }

  return {
    get:   <T>(path: string, opts?: RequestOptions) => request<T>('GET', path, undefined, opts),
    post:  <T>(path: string, body?: unknown, opts?: RequestOptions) => request<T>('POST', path, body, opts),
    put:   <T>(path: string, body?: unknown, opts?: RequestOptions) => request<T>('PUT', path, body, opts),
    patch: <T>(path: string, body?: unknown, opts?: RequestOptions) => request<T>('PATCH', path, body, opts),
    del:   <T>(path: string, body?: unknown, opts?: RequestOptions) => request<T>('DELETE', path, body, opts),
  }
}
