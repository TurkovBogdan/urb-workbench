// What the detail page's rail shows — and who tells it.
//
// The rail itself lives in `DetailShell` and survives transitions between detail pages: moving to
// another artifact changes only the content on the right, while the exit bar, search and table of
// contents rebuild in place without flicker. So a page doesn't render the rail, it FILLS it —
// through this registry.
//
// The registry doesn't hold the search string: it belongs to the page's store (it also drives the
// filtering of the page's sections), so what arrives here is a "current value + how to write it"
// pair.
import { onActivated, onDeactivated, onMounted, onUnmounted, ref, shallowRef, watchEffect } from 'vue'

import type { NavSection } from '@/components/SectionNav.vue'

export interface DetailRailSearch {
  label: string
  value: string
  update: (query: string) => void
  /** "Items found: N" — empty when not searching. */
  summary: string
  /** Label of the catching-up half of the search ("searching in texts…") — empty when there is
      nowhere left to search. While it is there, the counter next to it is provisional, and the
      spinner beside it says so. */
  pending?: string
}

export interface DetailRailConfig {
  /** Fallback exit address: the nearest parent in the tree. */
  parent: string
  /** Name of the fallback place — shown on the button when arriving via a direct link. */
  label: string
  /** Code of the shown object: a copy button for it appears in the exit row. Empty while the
      page is loading. */
  code?: string
  /** The page shows a document: an appearance gear appears in the exit row. */
  appearance?: boolean
  sections?: NavSection[]
  search?: DetailRailSearch
}

const config = shallowRef<DetailRailConfig | null>(null)

/** Read by the rail. */
export function detailRail() {
  return config
}

/**
 * Filled by the page. The built value recomputes itself while the page is on screen.
 *
 * The on-screen check is mandatory: `KeepAlive` doesn't unmount a view that was left, and its
 * effect would keep overwriting the rail with the old page's data on top of the new one.
 */
export function useDetailRail(build: () => DetailRailConfig): void {
  const onScreen = ref(false)

  onMounted(() => { onScreen.value = true })
  onActivated(() => { onScreen.value = true })
  onDeactivated(() => { onScreen.value = false })
  onUnmounted(() => { onScreen.value = false })

  watchEffect(() => {
    if (onScreen.value) config.value = build()
  })
}
