import type { RouteRecordNormalized, Router } from 'vue-router'

// A route component is a lazy `import()`, and it downloads INSIDE the navigation: while the chunk
// is in flight the old page stands still, and the progress bar with its 140 ms threshold doesn't
// get to appear (measured: first visit to the research detail page — 107 ms, second — 26 ms). The
// click looks like "nothing happened", and only then does everything come alive at once.
//
// The cure is for the chunk to arrive before the click. Two entries: hover or focus on an internal
// link (the cursor reaches the target before the press) and warm-up when idle — hover doesn't
// reach table rows and cards that are not links.
//
// The design-system showcase is excluded from warm-up: forty-seven pages that are not on the
// working path, and each will arrive on hover by itself.
const SHOWCASE_PREFIX = '/design-system'

// Remember the route RECORD, not the address: a detail page has its own address per code, but one
// chunk.
const warmed = new WeakSet<RouteRecordNormalized>()

function warm(record: RouteRecordNormalized): void {
  if (warmed.has(record)) return
  warmed.add(record)
  for (const component of Object.values(record.components ?? {})) {
    // A lazy component is a loader function; an already resolved route yields the object itself.
    // Failures are swallowed: this is anticipation, not a request, and navigation itself will
    // show the real error.
    if (typeof component === 'function') void (component as () => Promise<unknown>)().catch(() => {})
  }
}

function warmPath(router: Router, path: string): void {
  for (const record of router.resolve(path).matched) warm(record)
}

function internalHref(target: EventTarget | null): string | null {
  const anchor = (target as Element | null)?.closest?.('a[href]')
  const href = anchor?.getAttribute('href') ?? ''
  return href.startsWith('/') ? href : null
}

function whenIdle(task: () => void): void {
  const idle = (window as { requestIdleCallback?: (cb: () => void, opts?: { timeout: number }) => void })
    .requestIdleCallback
  if (idle) idle(task, { timeout: 3000 })
  else setTimeout(task, 1000)
}

export function setupRoutePrefetch(router: Router): void {
  const probe = (event: Event) => {
    const href = internalHref(event.target)
    if (href) warmPath(router, href)
  }

  document.addEventListener('pointerover', probe, { passive: true })
  document.addEventListener('focusin', probe)

  whenIdle(() => {
    for (const record of router.getRoutes()) {
      if (!record.path.startsWith(SHOWCASE_PREFIX)) warm(record)
    }
  })
}
