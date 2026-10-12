<script setup lang="ts">
// A help mark next to a field or section name: a grey "?" that explains the field on hover or focus.
//
// For an explanation that is needed once, not at every look: a subtitle under the name is read
// every time the card is on screen, while this one stays out of the way until asked. Grey, not the
// accent colour of `ChartInfo`: it sits beside a title and must not compete with it.
import { IconHelpCircle } from '@tabler/icons-vue'

withDefaults(defineProps<{
  text: string
  /**
   * The "?" is a Tab stop of its own. Off where it stands between two fields filled in one go —
   * a form dialog — and would break the walk from one field to the next. The text stays in
   * `aria-label` and on hover.
   */
  tabbable?: boolean
}>(), {
  tabbable: true,
})
</script>

<template>
  <VTooltip location="top" max-width="320">
    <template #activator="{ props: tooltip }">
      <span
        v-bind="tooltip"
        class="help-hint"
        :tabindex="tabbable ? 0 : -1"
        role="img"
        :aria-label="text"
      >
        <IconHelpCircle :size="15" :stroke-width="1.6" />
      </span>
    </template>
    <span class="help-hint__text">{{ text }}</span>
  </VTooltip>
</template>

<style scoped>
.help-hint {
  display: inline-flex;
  flex: none;
  color: var(--text-faint);
  cursor: help;
  transition: color 0.15s;
}

.help-hint:hover,
.help-hint:focus-visible {
  color: var(--text-muted);
  outline: none;
}

/* A line break in the text is kept: an explanation followed by an example reads as two parts. */
.help-hint__text {
  white-space: pre-line;
}
</style>
