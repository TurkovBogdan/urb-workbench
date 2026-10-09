<script setup lang="ts">
import { ref, nextTick, onMounted, onActivated, watch } from 'vue'
import { useRoute, onBeforeRouteLeave } from 'vue-router'
import { useLayoutStore } from '../store'
import { scrollClass } from '@/router/meta'
import { isBackNavigation } from '@/router/scroll'
import { restoreScrollTop } from '@/composables/useScrollRestore'

// `nested` is set by a frame that hosts a nested `RouterView` (`DetailShell`): it survives an
// address change, and so must start the new page itself — snapshot its meta and scroll back to the
// top. A regular page doesn't do this: its layout leaves together with it.
const props = withDefaults(defineProps<{ nested?: boolean }>(), { nested: false })

const layout = useLayoutStore()
const route  = useRoute()

const contentRef = ref<HTMLElement | null>(null)

// The reading position belongs to the address, not the view: KeepAlive keeps ONE instance per
// route, and two researches in a row share it along with that position — without a key the second
// would open at the first one's scroll.
const scrollByPath = new Map<string, number>()

// Layout meta is snapshotted NON-reactively, not read live from `route`. PageLayout
// sits inside the content <Transition mode="out-in">, which keeps the leaving page
// mounted while the global route already points at the destination — a reactive read
// would flip this (still-visible) page's padding/scroll to the next page's values
// mid-animation and cause a jerk. We re-snapshot only when this page (re)becomes
// current (mount / KeepAlive activate), so the outgoing page keeps its own classes.
const contentClass = ref<string[]>([])
function syncLayoutMeta() {
  contentClass.value = [
    'page-layout__content',
    scrollClass(route.meta.scroll),
    route.meta.padding !== false ? 'page-layout__content--padded' : '',
  ]
}

onBeforeRouteLeave(() => {
  scrollByPath.set(route.fullPath, contentRef.value?.scrollTop ?? 0)
})

// Going back through history (the "back" button on a zone or note page) also restores the reading
// position: the person continues where they left off. A regular transition opens a document rather
// than continuing it, so the list and the shelf lead to the top, even if that research was read
// before. "Returned or arrived" is asked IN `nextTick`, not right away: the router answers it in
// the scroll handler, which runs a tick after the address change. An answer read immediately would
// belong to the PREVIOUS transition, and a return would open at the top (for frame pages that wait
// for the leave animation the difference is invisible — for nested ones it shows at once).
function startPage(path: string) {
  syncLayoutMeta()
  nextTick(() => {
    const restored = isBackNavigation() ? scrollByPath.get(path) ?? 0 : 0
    if (contentRef.value) restoreScrollTop(contentRef.value, restored)
  })
}

onMounted(syncLayoutMeta)
onActivated(() => startPage(route.fullPath))

// A nested frame is not re-activated — the nested address changes instead, and that is the same
// moment: the leaving page's reading position is remembered, the incoming one opens at the top.
watch(() => route.fullPath, (path, previous) => {
  if (!props.nested) return
  scrollByPath.set(previous, contentRef.value?.scrollTop ?? 0)
  startPage(path)
})
</script>

<template>
  <div class="page-layout">

    <div v-if="layout.showTopBar && $slots.toolbar" class="page-layout__top">
      <slot name="toolbar" />
    </div>

    <div ref="contentRef" :class="contentClass">
      <slot />
    </div>

    <div v-if="layout.showBottomBar && $slots.footer" class="page-layout__bottom">
      <slot name="footer" />
    </div>

  </div>
</template>
