// Client for the INTERNAL API (zone `/internal/*`) — the single way the frontend talks to our
// own backend. The shared factory (`createClient`) plus THIS zone's policy; a separate client for a
// future external/public API is added the same way in one line. Callers pass zone-relative paths
// ('/workbench/tasks') — the prefix belongs to this file.
import { CLIENT_ID, CLIENT_ID_HEADER } from './client-id'
import { createClient } from './createClient'
import { errorText } from '@/api/errorText'
import { setShellError } from '@/composables/useShellError'
import { pushToast } from '@/composables/useToasts'

export { ApiError } from './createClient'
export type { ApiErrorBody, RequestOptions } from './createClient'

export const internalApi = createClient({
  prefix: '/internal',
  origin: import.meta.env.VITE_API_BASE ?? '',
  // Tab tag: the change feed uses it to tell the echo of our own edits from others' (`client-id.ts`).
  headers: { [CLIENT_ID_HEADER]: CLIENT_ID },
  // ⚠️ The zone has no auth today: there is no CSRF check on the backend, and turning this on
  // would add a failing GET `/internal/csrf-cookie` before every write. `loginPath` and
  // `onUnauthenticated` will appear here too, if login is ever introduced.
  csrf: false,
  // A permission denial is a screen at the current address, not a redirect to a separate one.
  onForbidden: () => setShellError('forbidden'),
  // A failure the screen did not show itself pops up as a toast.
  onError: (error) => pushToast(errorText(error)),
})
