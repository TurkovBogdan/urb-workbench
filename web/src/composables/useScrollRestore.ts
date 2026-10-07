// Restoring the reading position is not a single assignment: the page we returned to does not
// assemble instantly. Measured on the research detail page (returning from a zone): at activation
// its height is 1145px — data still arriving — 180ms later 5884, another 180 later 7452. A
// position assigned right away first hits the ceiling of the short page, and then the browser
// itself shifts it: content rendered above the viewport triggers scroll anchoring
// (`overflow-anchor`), and 900 turned into 2469 — exactly the height of the chunk that arrived.
//
// So the target is not set but HELD while the page grows into it. We let go for one of three
// reasons: the target is reached and holds, time runs out, or the person touched the scroll
// themselves — their intent outranks ours.
const HOLD_WINDOW_MS = 1200

// How the person takes the scroll back. Releasing early is not an option: the page grows in chunks,
// and in between the position can be right by accident — hold for the whole window, not "until it
// matches". `pointerdown` here is not about scrolling but about any touch on the page: a click in
// the table of contents is also a jump, and we have no right to fight it.
const USER_TAKEOVER_EVENTS = ['wheel', 'pointerdown'] as const

export function restoreScrollTop(element: HTMLElement, target: number): void {
  element.scrollTop = target
  if (target <= 0) return

  const deadline = performance.now() + HOLD_WINDOW_MS
  let released = false

  const release = () => {
    if (released) return
    released = true
    for (const event of USER_TAKEOVER_EVENTS) element.removeEventListener(event, release)
    window.removeEventListener('keydown', release)
  }

  for (const event of USER_TAKEOVER_EVENTS) element.addEventListener(event, release, { passive: true })
  window.addEventListener('keydown', release)

  const hold = () => {
    if (released) return
    if (performance.now() > deadline) return release()

    if (element.scrollTop !== target) element.scrollTop = target
    requestAnimationFrame(hold)
  }

  requestAnimationFrame(hold)
}
