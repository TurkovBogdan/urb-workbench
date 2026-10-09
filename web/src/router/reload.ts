import type { Router } from 'vue-router'
import { setShellError } from '@/composables/useShellError'

// A deploy removes the old Vite chunks (hash in the name), and in a tab opened before it a
// transition to a lazy route fails SILENTLY: navigation is cancelled, the screen stays the same —
// "click, and nothing". The right answer here is not a failure screen but a reload at THE SAME
// address: the fresh bundle will show the right page. A sessionStorage key prevents a loop if the
// chunk still isn't served after the reload.
const GUARD_KEY = 'app.chunk-reload'

// The dynamic import error text differs across browsers, and it has no common type.
const CHUNK_ERROR = /dynamically imported module|Importing a module script failed|Failed to fetch/i

function reloadOnce(path: string): void {
  // A reload at this address already happened and didn't help — only an honest failure screen left.
  if (sessionStorage.getItem(GUARD_KEY) === path) {
    sessionStorage.removeItem(GUARD_KEY)
    setShellError('failure')

    return
  }

  sessionStorage.setItem(GUARD_KEY, path)
  window.location.assign(path)
}

export function setupChunkReload(router: Router): void {
  // Two entries into the same scenario: `vite:preloadError` catches a failed module preload
  // (including outside navigation), `router.onError` — a failed lazy import of the route itself.
  window.addEventListener('vite:preloadError', () => {
    reloadOnce(window.location.pathname + window.location.search + window.location.hash)
  })

  router.onError((error, to) => {
    if (!(error instanceof Error) || !CHUNK_ERROR.test(error.message)) return

    reloadOnce(to.fullPath)
  })

  // Arrived — the safety catch is no longer needed.
  router.afterEach(() => {
    sessionStorage.removeItem(GUARD_KEY)
  })
}
