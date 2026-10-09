<script setup lang="ts">
// Drag handle — one for the whole app.
//
// One on purpose: the grab area size, ripple suppression, `touch-action`, focus ring and the
// screen-reader label are set here, and call sites differ only by the selector in sortable's `handle`.
// Once these five things drift apart you get five different handles, of which one works.
//
// WHY A HANDLE AT ALL. Without it the whole row is draggable, and then the row loses text selection,
// and on a touch device — scrolling: the gesture starts with the same motion. The handle separates
// "grab" and "scroll" into different parts of the row.
//
// `touch-action: none` is required and sits exactly on the handle: otherwise the browser swallows
// pointer events in favour of its own scrolling and the gesture never starts. It can't go on the
// whole row — then the list would stop scrolling by finger.
import { IconGripVertical } from '@tabler/icons-vue'

withDefaults(defineProps<{
  /** Screen-reader label: what exactly this handle moves. */
  label: string
  /** The handle is always visible, not only under the pointer on its row. */
  always?: boolean
}>(), {
  always: false,
})
</script>

<template>
  <span
    class="drag-handle"
    :class="{ 'drag-handle--always': always }"
    role="button"
    tabindex="-1"
    :aria-label="label"
    :title="label"
  >
    <IconGripVertical :size="14" :stroke-width="1.8" />
  </span>
</template>

<style scoped>
/* The box is wider than the icon: grabbing has to be precise, and a 14px glyph is no grab area. The
   size is taken from the height of a dense list row so the handle doesn't make the row taller. */
.drag-handle {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 20px;
  height: 28px;
  flex: none;
  color: var(--text-faint);
  cursor: grab;
  opacity: 0;
  transition: opacity 0.12s ease, color 0.12s ease;
  touch-action: none;
  user-select: none;
}

.drag-handle--always,
.drag-handle:focus-visible { opacity: 1; }

/* Appears on hovering the ROW, not itself: an invisible handle can't be found with the pointer. */
:where(.task-row, .drag-row):hover .drag-handle { opacity: 1; }

.drag-handle:hover { color: var(--text); }

.drag-handle:active { cursor: grabbing; }

/* A finger on a touch device doesn't hover: there the handle is always visible, otherwise nothing could summon it. */
@media (hover: none) {
  .drag-handle { opacity: 1; }
}
</style>
