<script setup lang="ts">
/**
 * Status picker: a list with icons and two buttons that step along the flow of work.
 *
 * Modelled on `TaskPrioritySelect`: status has an order too, and the neighbouring value is picked
 * more often than a jump across the whole set — from plan to work, from work to review. Opening
 * the list for a one-step move means three motions instead of one.
 *
 * The order is `TASK_STATUSES` as is: backlog, plan, work, two checks, two outcomes. It already
 * reads left to right as the flow of work, so unlike priority it does not need reversing. The
 * ends do not wrap: on "Backlog" the left button is disabled, on "Canceled" the right one.
 *
 * All call-site styling (`label`, `variant`, `density`, `disabled`, `loading`) passes straight
 * through as attributes: the field has no look of its own, the page it sits on owns it.
 */
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'

import VSelectStepper from '@/components/VSelectStepper.vue'
import { TASK_STATUSES, statusColor, statusIcon } from '../labels'

const model = defineModel<string>()

const { t } = useI18n()

const items = computed(() =>
  TASK_STATUSES.map((value) => ({ value, title: t(`tasks.task.status.${value}`) })),
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
    :prev-label="t('tasks.task.status_step.back')"
    :next-label="t('tasks.task.status_step.forward')"
  >
    <template #item="{ props: itemProps, item }">
      <VListItem v-bind="itemProps">
        <template #prepend>
          <span class="status-select__glyph" :class="`status-select__glyph--${statusColor(item.value)}`">
            <component :is="statusIcon(item.value)" :size="16" :stroke-width="1.6" />
          </span>
        </template>
      </VListItem>
    </template>

    <!-- `#selection` works only without chips — with them Vuetify renders `#chip` and silently
         ignores this slot. -->
    <template #selection="{ item }">
      <span class="status-select__line">
        <span class="status-select__glyph" :class="`status-select__glyph--${statusColor(item.value)}`">
          <component :is="statusIcon(item.value)" :size="16" :stroke-width="1.6" />
        </span>
        {{ item.title }}
      </span>
    </template>
  </VSelectStepper>
</template>

<style scoped>
/* The icon-to-label gap matches the list item's (`--v-list-prepend-gap`): the selected value is
   the same item, just shown in the field, and the two must not drift apart. */
.status-select__line {
  display: inline-flex;
  align-items: center;
  gap: 10px;
  min-width: 0;
}

/* Same colors as the glyph in the task list row: one status cannot be green in the table and
   grey in the field used to change it. */
.status-select__glyph {
  display: inline-flex;
  align-items: center;
  flex: none;
}

.status-select__glyph--accent  { color: var(--accent); }
.status-select__glyph--success { color: var(--success); }
.status-select__glyph--error   { color: var(--error); }
.status-select__glyph--warn    { color: var(--warn); }
.status-select__glyph--muted   { color: var(--text-faint); }
</style>
