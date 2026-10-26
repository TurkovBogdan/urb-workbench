// Bring an element into view by scrolling only the container that scrolls it.
//
// `scrollIntoView` scrolls every ancestor it can, `overflow: hidden` ones included — inside the page
// frame that drags the whole layout. Here the nearest ancestor that actually scrolls moves, by the
// least that shows the element whole, and nothing else does.

function scrollerOf(element: Element): HTMLElement | null {
  for (let node = element.parentElement; node; node = node.parentElement) {
    const { overflowY } = getComputedStyle(node)
    if ((overflowY === 'auto' || overflowY === 'scroll') && node.scrollHeight > node.clientHeight) return node
  }
  return document.scrollingElement instanceof HTMLElement ? document.scrollingElement : null
}

/** Scroll the element's own scroller just enough to show it; already in view — nothing moves. */
export function revealInScroller(element: Element, margin = 16): void {
  const scroller = scrollerOf(element)
  if (!scroller) return
  const box = element.getBoundingClientRect()
  const isRoot = scroller === document.scrollingElement
  const view = isRoot ? { top: 0, bottom: window.innerHeight } : scroller.getBoundingClientRect()
  let delta = 0
  if (box.bottom + margin > view.bottom) delta = box.bottom + margin - view.bottom
  if (box.top - margin < view.top + delta) delta = box.top - margin - view.top
  if (!delta) return
  const still = window.matchMedia('(prefers-reduced-motion: reduce)').matches
  scroller.scrollBy({ top: delta, behavior: still ? 'auto' : 'smooth' })
}
