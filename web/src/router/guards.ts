import { watch } from 'vue'
import type { RouteLocationNormalized, Router } from 'vue-router'
import { startNavigationProgress, stopNavigationProgress } from './progress'
import { dismissHoverTooltips } from './overlays'
import { recordNavigation } from '@/composables/useNavigationHistory'
import { beginRouteTransition, endRouteTransition } from '@/composables/useRouteTransition'
import { clearShellError } from '@/composables/useShellError'
import { i18n } from '@/plugins/i18n'

const APP_NAME = 'Uroboros.Workbench'

// The tab title is part of navigation, not decoration: a route change doesn't update it by itself,
// a screen reader reads it first, and research work means many open tabs. A route without
// `meta.title` leaves just the app name rather than a made-up string.
function applyDocumentTitle(to: RouteLocationNormalized): void {
  const key = to.meta.title
  document.title = key ? `${i18n.global.t(key)} — ${APP_NAME}` : APP_NAME
}

// After a transition focus stays on the clicked link: for keyboard and screen reader users
// "nothing happened" becomes literal. Move it to the content zone.
function focusContent(): void {
  const main = document.querySelector<HTMLElement>('.main-content')
  if (!main) return

  main.setAttribute('tabindex', '-1')
  main.focus({ preventScroll: true })
}

export function setupGuards(router: Router): void {
  router.beforeEach(() => {
    // Close any hover tooltip before KeepAlive deactivates its page and orphans the
    // teleported overlay (the activator's mouseleave never fires on a navigating click).
    dismissHoverTooltips()

    // A failure screen belongs to the address it was shown at: leaving the address clears it.
    clearShellError()

    // Before the new view mounts: it must see the transition already started, otherwise it would
    // defer its heavy content not until the animation but into nowhere. The transition itself
    // clears the flag.
    beginRouteTransition()

    // Arm the content-zone loading bar; the show-delay swallows instant swaps.
    startNavigationProgress()
    return true
  })

  // Destination resolved (incl. lazy chunk loaded) — drop the bar.
  router.afterEach((to, from, failure) => {
    recordNavigation(from)
    stopNavigationProgress()
    applyDocumentTitle(to)
    focusContent()
    // A failed transition (repeat navigation to the same address, a cancel) never reaches the
    // animation, and nobody would clear the flag — the page stayed the same, and there is no
    // enter left to wait for.
    //
    // A transition WITHIN one route ends the same way (only a param changed: task → its subtask):
    // the component is the same, `<Transition>` doesn't recreate it and doesn't emit
    // `after-enter`. Leave the flag raised — and all heavy content mounted afterwards will wait
    // for an animation that will never come: the markup arrives empty.
    if (failure || to.name === from.name) endRouteTransition()
  })
  // Aborted/failed navigation never reaches afterEach — clear the bar here too.
  router.onError(() => stopNavigationProgress())

  // Switching the language is not a navigation, so afterEach never re-titles the tab.
  watch(i18n.global.locale, () => applyDocumentTitle(router.currentRoute.value))
}
