import type { RouteLocationNormalized } from 'vue-router'

// A history return or a new transition — the only thing the router knows about scrolling, and the
// only thing a page needs. `savedPosition` tells them apart: the browser hands it to the router
// only on back/forward, while on a regular transition (a link click, `router.push`) it is `null`.
//
// The router itself scrolls nothing: what scrolls is not the window but the content zone
// (`PageLayout`), and it restores the position itself — this module only answers "were we brought
// back here, or did we arrive here".
let backNavigation = false

export function trackNavigationKind(
  _to: RouteLocationNormalized,
  _from: RouteLocationNormalized,
  savedPosition: { left: number; top: number } | null,
): false {
  backNavigation = savedPosition !== null
  return false
}

export function isBackNavigation(): boolean {
  return backNavigation
}
