import { readonly, ref } from 'vue'
import type { ErrorKind } from '@/constants/errors'

// A failure the shell shows INSTEAD of the route's content, without touching the address bar: the
// address stays the one the person arrived at. Redirecting to a separate `/403` would erase the
// only clue — what exactly was being opened — and with it break both support requests and
// analytics.
//
// Set by: the API client (403 on a read), the render error handler, the navigation failure
// handler. Cleared by any subsequent navigation (a guard at the start of every transition).
const kind = ref<ErrorKind | null>(null)

export const shellError = readonly(kind)

export function setShellError(next: ErrorKind): void {
  kind.value = next
}

export function clearShellError(): void {
  kind.value = null
}
