<script setup lang="ts">
// Copy chip: the copy icon and the text — one button.
//
// The icon comes FIRST: it tells what the chip is before the eye finishes reading the value, and it
// doesn't drift with the text length — chips of different lengths keep their icons in one line.
//
// For anything a person takes to the clipboard to paste elsewhere: an object code, an address, a
// token, a path. There used to be a separate 22px icon button next to the text that had to be aimed
// at, while the text beside it did nothing. Here the whole chip is the target, and exactly what is
// written on it gets copied (or `text`, if something else is shown).
//
// At rest the chip is transparent and reads as plain text: copying is a side action with no need to
// call attention to itself. The fill under the pointer gives it away as a button — the same as the
// counter button's. Success is shown by the icon turning into a check, without color: people copy
// many times over, and a green flash would read as an event.
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { IconCheck, IconCopy } from '@tabler/icons-vue'

import { useClipboard } from '@/composables/useClipboard'

const props = defineProps<{
  /** What goes to the clipboard. */
  text: string
  /** What is written on the chip; if not passed — `text` itself. */
  label?: string
  /** Action label for the tooltip and screen reader; defaults to "Copy". */
  hint?: string
}>()

const { t } = useI18n()
const { copy, isCopied } = useClipboard()

const copied = computed(() => isCopied(props.text))
const hintText = computed(() =>
  copied.value ? t('common.action.copied') : (props.hint ?? t('common.action.copy')),
)
</script>

<template>
  <!-- The click doesn't propagate past the chip: it also sits in rows that open on click, and
       "copy" must not navigate away from the page as a side effect. -->
  <button
    type="button"
    class="copy-chip"
    :aria-label="`${hintText}: ${props.label ?? props.text}`"
    @click.stop="copy(props.text)"
  >
    <IconCheck v-if="copied" :size="14" :stroke-width="1.8" class="copy-chip__icon" />
    <IconCopy v-else :size="14" :stroke-width="1.6" class="copy-chip__icon" />
    <span class="copy-chip__text">{{ props.label ?? props.text }}</span>
    <VTooltip activator="parent" location="top">{{ hintText }}</VTooltip>
  </button>
</template>

<style scoped>
/* The look comes from the counter button (`CounterButton.vue`): interface font, small size, muted
   color, a fill only under the pointer. The typeface is `--font`, not inherited: the chip sits both
   in headers and in rows, and must look the same wherever it is placed.

   Text and icon sit in boxes of one height (14px): with different heights flex yields fractional
   offsets, the browser rounds them differently, and the text sits a pixel above the icon. */
.copy-chip {
  display: inline-flex;
  flex: none;
  align-items: center;
  gap: 4px;
  max-width: 100%;
  height: 22px;
  padding: 0 5px;
  border: 0;
  border-radius: 6px;
  background: transparent;
  font-family: var(--font);
  font-size: 12px;
  font-weight: 400;
  line-height: 14px;
  letter-spacing: normal;
  color: var(--copy-chip-color, var(--text-muted));
  cursor: pointer;
  transition: background-color 120ms ease, color 120ms ease;
}

.copy-chip:hover,
.copy-chip:focus-visible {
  background: var(--border-soft);
  color: var(--text);
  outline: none;
}

/* A long value (a path, a token) shrinks with an ellipsis, the icon never does: without it the chip
   no longer says that it can be clicked. */
.copy-chip__text {
  min-width: 0;
  overflow: hidden;
  white-space: nowrap;
  text-overflow: ellipsis;
}

/* The icon is quieter than the text: it explains the action rather than naming the value. */
.copy-chip__icon {
  flex: none;
  color: var(--text-faint);
}

.copy-chip:hover .copy-chip__icon,
.copy-chip:focus-visible .copy-chip__icon {
  color: inherit;
}
</style>
