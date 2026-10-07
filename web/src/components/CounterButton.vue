<script setup lang="ts">
// Counter button: icon, number and collapse arrow — one target.
//
// One for the whole app: both a task row with subtasks and a group card header carry it. While
// there were two styles they drifted apart — the group count was set differently from the row
// count, and neighbouring buttons read as different objects. Call sites differ only in icon and label.
//
// Everything is packed into one button because on its own the arrow is a 20px target that is hard
// to hit, while the icon and number next to it look clickable and do nothing. The count comes
// first: it answers whether expanding is worth it.
//
// Click and Enter don't propagate past the button: on them a task row opens the task, and
// collapsing a branch and leaving the list in one press is not what the person asked for.
import type { Component } from 'vue'
import { IconChevronDown, IconChevronRight } from '@tabler/icons-vue'

const props = defineProps<{
  /** What is being counted: subtasks for a row, tasks for a group. */
  icon: Component
  /** Not passed — no number, the icon and arrow remain. Zero is shown: it is an answer too. */
  count?: number
  /** Content is collapsed: the arrow points sideways, where it will slide out from. */
  folded: boolean
  /** The action label — for screen readers and the tooltip; depends on `folded`, the caller knows it. */
  label: string
}>()

const emit = defineEmits<{ toggle: [] }>()
</script>

<template>
  <button
    type="button"
    class="counter-button"
    :aria-expanded="!props.folded"
    :aria-label="props.label"
    @click.stop="emit('toggle')"
    @keydown.enter.stop
  >
    <component :is="props.icon" :size="14" :stroke-width="1.6" />
    <span v-if="props.count !== undefined" class="counter-button__number">{{ props.count }}</span>
    <component :is="props.folded ? IconChevronRight : IconChevronDown" :size="14" :stroke-width="1.8" />
    <VTooltip activator="parent" location="top">{{ props.label }}</VTooltip>
  </button>
</template>

<style scoped>
/* Looks like an annotation, not a button: small size and a muted color. Only the fill under the
   pointer gives it away as a button — the area around the icons is the target. The font is reset
   entirely: the button sits both in a bold group name and in a plain row, and has nothing to
   inherit there. The typeface is the interface font (`--font`), neither inherited nor named: the
   person picks it in settings, and the button must change along with the rest of the interface.

   The number is 11px with regular digits. Compared live against 12px with fixed-width digits
   (`tabular-nums`) and against monospace: tabular digits are wide and look coarse next to a 13px
   name, monospace reads as foreign. The button changes width slightly when the number
   changes — cheaper than coarse digits in every row.

   The resting color is set by the call site via `--counter-button-color`: both the row and the card
   reveal the button when the pointer is over them, not only over the button itself. A variable, not
   an outside rule: a foreign rule with its own specificity would override hover on the button itself.

   All three parts sit in boxes of the same height, 14px: the icons and the number's line
   (`line-height`). Flex centers them, and with different heights the offset inside the button is
   fractional (5.5px for an 11px line, 4.5px for a 13px arrow). The browser rounds such offsets
   differently, and on screen the number sat a pixel above the icon. With equal boxes every offset
   is whole and identical. */
.counter-button {
  display: inline-flex;
  flex: none;
  align-items: center;
  gap: 3px;
  height: 22px;
  padding: 0 4px;
  border: 0;
  border-radius: 6px;
  background: transparent;
  font-family: var(--font);
  font-size: 11px;
  font-weight: 400;
  line-height: 14px;
  letter-spacing: normal;
  color: var(--counter-button-color, var(--text-faint));
  cursor: pointer;
  transition: background-color 120ms ease, color 120ms ease;
}

.counter-button:hover,
.counter-button:focus-visible {
  background: var(--border-soft);
  color: var(--text);
  outline: none;
}
</style>
