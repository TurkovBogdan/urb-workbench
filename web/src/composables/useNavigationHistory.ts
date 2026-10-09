import { computed, shallowRef, type ComputedRef } from 'vue'
import type { RouteLocationNormalized, RouteLocationRaw, Router } from 'vue-router'

// The route we arrived from to reach the current page, or null on a direct entry
// (deep link / reload / new tab) where vue-router's START_LOCATION has no matched records.
//
// Reactive, because not only the button's behaviour depends on it but also its label: going back
// through history leads "where you came from", while the fallback address leads to a specific
// place, which is called by its own name.
const previousRoute = shallowRef<RouteLocationNormalized | null>(null)

export function recordNavigation(from: RouteLocationNormalized): void {
  previousRoute.value = from.matched.length > 0 ? from : null
}

export function useNavigationHistory(): {
  goBack: (router: Router, fallback: RouteLocationRaw) => void
  hasHistory: ComputedRef<boolean>
} {
  function goBack(router: Router, fallback: RouteLocationRaw): void {
    if (previousRoute.value) router.back()
    else router.push(fallback)
  }

  /** There is history to go back to — so the fallback address won't be needed this time. */
  const hasHistory = computed(() => previousRoute.value !== null)

  return { goBack, hasHistory }
}
