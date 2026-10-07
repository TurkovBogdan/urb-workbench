<script setup lang="ts">
/**
 * Priority picker: a list with icons and two buttons that step along the importance ladder.
 *
 * A separate component because there are already two places to pick it — the task card and the
 * create form — and a priority item is not a bare string: order, icon and color live in
 * `labels.ts`, and assembling them anew in each window would diverge at the first edit of the
 * vocabulary.
 *
 * The buttons are the design system's `VSelectStepper`: priority is a ladder, and the next rung is
 * picked more often than a jump across the whole set. The set is reversed from frozen to burning —
 * the opposite of `TASK_PRIORITIES`, where the most important comes first: a scale is read bottom
 * up, and then moving right matches rising importance, as on any slider. The ends do not wrap — on
 * frozen the left button is disabled, on burning the right one.
 *
 * All call-site styling (`label`, `variant`, `density`, `disabled`) passes straight through as
 * attributes: the field has no look of its own, the window it sits in owns it.
 */
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'

import VSelectStepper from '@/components/VSelectStepper.vue'
import { TASK_PRIORITIES, priorityColor, priorityIcon } from '../labels'

const model = defineModel<string>()

const { t } = useI18n()

// Copying before reversing is mandatory: `TASK_PRIORITIES` is a shared vocabulary, and `reverse`
// on it in place would flip the order in the filters and everywhere else it is read.
const items = computed(() =>
  [...TASK_PRIORITIES]
    .reverse()
    .map((value) => ({ value, title: t(`tasks.task.priority.${value}`) })),
)
</script>

<template>
  <!-- The icon is derived from the item's value, not from a field of its own: `item` reaches the
       slot in two different shapes (the source object and the Vuetify wrapper), and only `value`
       and `title` exist on both. -->
  <VSelectStepper
    v-model="model"
    :items="items"
    :chips="false"
    :prev-label="t('tasks.task.priority_step.lower')"
    :next-label="t('tasks.task.priority_step.raise')"
  >
    <template #item="{ props: itemProps, item }">
      <VListItem v-bind="itemProps">
        <template #prepend>
          <span class="priority-select__glyph" :class="`priority-select__glyph--${priorityColor(item.value)}`">
            <component :is="priorityIcon(item.value)" :size="16" :stroke-width="1.6" />
          </span>
        </template>
      </VListItem>
    </template>

    <!-- `#selection` works only without chips — with them Vuetify renders `#chip` and silently
         ignores this slot. -->
    <template #selection="{ item }">
      <span class="priority-select__line">
        <span class="priority-select__glyph" :class="`priority-select__glyph--${priorityColor(item.value)}`">
          <component :is="priorityIcon(item.value)" :size="16" :stroke-width="1.6" />
        </span>
        {{ item.title }}
      </span>
    </template>
  </VSelectStepper>
</template>

<style scoped>
/* The icon-to-label gap matches the list item's (`--v-list-prepend-gap`): the selected value is
   the same item, just shown in the field, and the two must not drift apart. */
.priority-select__line {
  display: inline-flex;
  align-items: center;
  gap: 10px;
  min-width: 0;
}

/* Same colors as the glyph in the task list row: one priority cannot be red on the card and grey
   in the field used to change it. */
.priority-select__glyph {
  display: inline-flex;
  align-items: center;
  flex: none;
}

.priority-select__glyph--accent  { color: var(--accent); }
.priority-select__glyph--success { color: var(--success); }
.priority-select__glyph--error   { color: var(--error); }
.priority-select__glyph--warn    { color: var(--warn); }
.priority-select__glyph--muted   { color: var(--text-faint); }
</style>
