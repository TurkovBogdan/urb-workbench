<script setup lang="ts">
// The portal's whole modal window: card, header with a close ×, body and button bar. Assembling
// `VDialog` + `VCard` by hand is no longer needed — so the window anatomy can't diverge across
// screens, and Vuetify's traps (`VCardTitle`, `VCardActions`) never make it into the code.
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import DialogHeader from './DialogHeader.vue'
import DialogActions from './DialogActions.vue'

// Width is a window parameter, but not an arbitrary one: four steps by purpose instead of a
// scatter of literals.
const WIDTHS = {
  narrow: 440,  // confirmation, a short question
  base: 560,    // form, detail view
  wide: 900,    // two columns, payment
  xwide: 1180,  // workspace: a prose column with a fields column beside it (task detail)
}

const open = defineModel<boolean>({ required: true })

const props = withDefaults(defineProps<{
  title: string
  description?: string
  size?: keyof typeof WIDTHS
  /** Doesn't close on an outside click or Esc: the only way out is the × and the buttons. */
  persistent?: boolean
  /** The rule under the header. Drop it for a window WITHOUT a content block (a question with no content). */
  rule?: boolean
  /** Work in progress: the × is visible but doesn't work. */
  closeDisabled?: boolean
  /** Body to the card edges — for content with its own background (payment columns). */
  flush?: boolean
  /** Long content: the body scrolls, the header and buttons stay in place. */
  scrollable?: boolean
}>(), {
  description: undefined,
  size: 'base',
  persistent: false,
  rule: true,
  closeDisabled: false,
  flush: false,
  scrollable: false,
})

const slots = defineSlots<{
  default(): unknown
  actions?(): unknown
  /** Actions on the window content — in the header, right after the ×. */
  headerActions?(): unknown
  /** The window title when it isn't a string: the detail view's editable field. */
  title?(): unknown
  /** The line under the title when it holds more than text: a code with a copy button. */
  description?(): unknown
}>()

const maxWidth = computed(() => WIDTHS[props.size])

// Without buttons the body itself owns the card's bottom padding. Check the slot, not `:last-child`:
// VCard appends `.v-card__underlay` as the last child and a positional selector misses.
const hasActions = computed(() => Boolean(slots.actions))

// ── Smooth height change ──────────────────────────────────────────────────────────────────
// Content changes after opening: a payment widget finished loading, a tab was switched, a form
// turned into "sent". A jump reads as a jerk — the window is centered, so both edges move.
//
// Animate the body WRAPPER, not the card: Vuetify makes the card a flex item with
// `flex: 1 1 var(--v-card-height, 100%)`, and the `height` property has no effect on it at all.
// The wrapper gets an explicit height for the duration of the transition and is released back to
// `auto` so the content drives the size itself again.
const sizer = ref<HTMLElement | null>(null)
const content = ref<HTMLElement | null>(null)

let observer: ResizeObserver | null = null

// We remember the height OURSELVES: the observer fires after layout, by which point the wrapper
// already equals the new content — comparing the two is pointless, no difference shows.
let previous: number | null = null

function release(): void {
  const element = sizer.value
  if (element === null) return

  element.style.height = ''
  element.style.overflow = ''
}

function onContentResize(): void {
  const element = sizer.value
  if (element === null || content.value === null) return

  const next = content.value.offsetHeight
  if (previous === null || next === previous) {
    previous = next
    return
  }

  const from = previous
  previous = next

  // Hide overflow only during the motion: at rest, needed things may stick out of the window.
  element.style.overflow = 'hidden'
  element.style.height = `${from}px`
  void element.offsetHeight  // reflow: without it the browser merges both values into one
  element.style.height = `${next}px`
  element.addEventListener('transitionend', release, { once: true })
}

function stopWatching(): void {
  observer?.disconnect()
  observer = null
  previous = null
}

// Watch the element ITSELF, not `open`: the window content mounts after opening, and at the moment
// the model changes it isn't there yet.
watch(content, (element) => {
  stopWatching()

  if (element === null) return

  // Smoothness is decoration: with animation turned off in the system the window resizes at once.
  if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) return

  observer = new ResizeObserver(onContentResize)
  observer.observe(element)
})

onBeforeUnmount(stopWatching)
</script>

<template>
  <VDialog
    v-model="open"
    :max-width="maxWidth"
    :persistent="persistent"
    :scrollable="scrollable"
  >
    <VCard>
      <DialogHeader
        :title="title"
        :description="description"
        :rule="rule"
        :close-disabled="closeDisabled"
        @close="open = false"
      >
        <template v-if="slots.title" #title><slot name="title" /></template>
        <template v-if="slots.description" #description><slot name="description" /></template>
        <template v-if="slots.headerActions" #actions><slot name="headerActions" /></template>
      </DialogHeader>

      <div
        class="app-dialog__body"
        :class="{
          'app-dialog__body--flush': flush,
          'app-dialog__body--last': !hasActions,
          'app-dialog__body--tight': !rule,
          'app-dialog__body--scrollable': scrollable,
        }"
      >
        <div ref="sizer" class="app-dialog__sizer">
          <div ref="content">
            <slot />
          </div>
        </div>
      </div>

      <DialogActions v-if="hasActions">
        <slot name="actions" />
      </DialogActions>
    </VCard>
  </VDialog>
</template>

<style scoped>
/* Typography repeats the former VCardText — the window body is set smaller than the page.
   Below is half the gap to the buttons; DialogActions brings the other half. */
.app-dialog__body {
  padding: 16px 24px 12px;
  font-size: 13px;
  line-height: 1.5;
  color: var(--text);
}

/* The body ITSELF scrolls, not a nested block: otherwise the scrollbar sits at the inner edge of
   the padding and hangs 24px from the card border. The window caps the height (`scrollable` on
   VDialog makes the card a column), so there is no max-height of its own here. */
.app-dialog__body--scrollable {
  flex: 1 1 auto;
  overflow-y: auto;
}

/* No buttons — the body holds the card's bottom and mirrors the header's top. */
.app-dialog__body--last { padding-bottom: 22px; }

/* No rule — the header alone sets the distance to the text, otherwise two paddings add up. */
.app-dialog__body--tight { padding-top: 0; }

.app-dialog__body--flush { padding: 0; }

/* The script sets an explicit height while content changes; at rest it is `auto`. */
.app-dialog__sizer { transition: height 220ms cubic-bezier(.4, 0, .2, 1); }
</style>
