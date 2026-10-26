<script setup lang="ts">
// The hover card over an entity pill. Both zones drive it the same way: `hover(pill, code)` when
// the pointer reaches a pill, `leave()` when it goes. The viewer keeps one per body and points it
// at whichever pill is under the pointer (its pills are plain HTML); the editor keeps one per pill.
//
// It opens after a short pause — a pointer crossing a line of pills must not flash a card per pill
// — and closes after a shorter one, so the pointer can travel from the pill onto the card and stay.
// It never takes focus: in the editor the caret stays where the person left it.
import { ref, watch } from 'vue'
import { usePageActive } from '@/composables/usePageActive'
import EntityPreviewCard from './EntityPreviewCard.vue'

const OPEN_DELAY_MS = 400
const CLOSE_DELAY_MS = 150

const open = ref(false)
const target = ref<HTMLElement>()
const code = ref('')

let openTimer: ReturnType<typeof setTimeout> | undefined
let closeTimer: ReturnType<typeof setTimeout> | undefined

// A click on a pill navigates within the pause, and the pointer that stays put sends no `leave`:
// the timer fired on the next page, opened the card over a pill no longer in the document, and the
// card stood in its top left corner. Opening from code passes by the page frame's `disabled`, so
// the card asks itself whether its page and its pill are still there.
const pageActive = usePageActive()

watch(pageActive, (active) => {
  if (active) return
  clearTimeout(openTimer)
  clearTimeout(closeTimer)
  open.value = false
})

function hover(pill: HTMLElement, pillCode: string): void {
  clearTimeout(closeTimer)
  clearTimeout(openTimer)
  if (open.value && target.value === pill) return
  // Moving from one pill to the next while a card is up swaps it at once.
  const pause = open.value ? 0 : OPEN_DELAY_MS
  openTimer = setTimeout(() => {
    if (!pageActive.value || !pill.isConnected) return
    target.value = pill
    code.value = pillCode
    open.value = true
  }, pause)
}

function leave(): void {
  clearTimeout(openTimer)
  clearTimeout(closeTimer)
  closeTimer = setTimeout(() => { open.value = false }, CLOSE_DELAY_MS)
}

function stay(): void {
  clearTimeout(closeTimer)
}

defineExpose({ hover, leave })
</script>

<template>
  <VMenu
    v-model="open"
    :target="target"
    location="bottom start"
    :offset="6"
    :open-on-click="false"
    :close-on-content-click="false"
    :capture-focus="false"
    scroll-strategy="close"
    content-class="ref-preview-menu"
  >
    <VCard variant="outlined" rounded="lg" class="ref-preview-menu__card" @mouseenter="stay" @mouseleave="leave">
      <EntityPreviewCard :code="code" @opened="open = false" />
    </VCard>
  </VMenu>
</template>

<style>
/* The card sits on the page's surface like the other popovers, not on the document's background. */
.ref-preview-menu .ref-preview-menu__card {
  background: rgb(var(--v-theme-surface));
  box-shadow: 0 4px 16px rgba(0, 0, 0, 0.12);
}
</style>
