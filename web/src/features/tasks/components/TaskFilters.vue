<script setup lang="ts">
// Task list filter panel: what narrows the results and what brings them back.
//
// The panel belongs to the PAGE, not to the display format: a board will be narrowed by the same
// controls as the list, and a second copy of them alongside would diverge from the first at the
// very first new filter. So the panel is a separate component, and a format receives it via a slot
// and only finds it a place (for the list — inside its card above the ruler).
//
// EVERYTHING IN VIEW. The controls stand in a row, with no button that opens them as a list: a
// collapsed panel saved space but paid for it with two motions instead of one.
//
// The frame, the field widths and the applied line with reset come from the shared `FilterPanel`;
// this component brings only what is specific to tasks — the controls and what they mean in the
// store. The schema-driven `ListFilters` does not fit here: a scoped search, a multi-select status
// with icons and two inverted "show more" flags are outside search / select / toggle.
//
// ROW ORDER: search, vocabularies, toggles. Search comes first — it is always used, and it is the
// only thing people look at the panel for without meaning to configure anything. Last comes the
// "show beyond the usual" group: the list hides finished and deleted by default, and these two
// buttons WIDEN the results rather than narrow them, so they stand apart from the vocabularies,
// pushed to the right edge.
//
// All values live in the list store, not here: the filters survive leaving the page and coming
// back, while local component state would reset on every remount.
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { IconCircleCheck, IconTrash } from '@tabler/icons-vue'

import FilterPanel, { type AppliedFilter } from '@/components/FilterPanel.vue'
import SearchField from '@/components/SearchField.vue'

import { useTasksStore } from '../stores/tasks.store'
import { taskScopesModel, taskSearchScopes } from '../search'
import {
  TASK_PRIORITIES,
  TASK_STATUSES,
  priorityColor,
  priorityIcon,
  statusColor,
  statusIcon,
} from '../labels'

const { t } = useI18n()
const store = useTasksStore()

// The status field shows the FIRST selected value in full and the rest as a counter: the field
// must stay one line, and two values with icons do not fit at any reasonable width. The whole set
// is visible as chips under the controls anyway.

// Keys of the "show beyond the usual" group — one group for two independent toggles.
const EXTRA_FINISHED = 'finished'
const EXTRA_DELETED = 'deleted'

const statusItems = computed(() =>
  TASK_STATUSES.map((value) => ({ value, title: t(`tasks.task.status.${value}`) })),
)
const priorityItems = computed(() =>
  TASK_PRIORITIES.map((value) => ({ value, title: t(`tasks.task.priority.${value}`) })),
)

const query = computed({
  get: () => store.query,
  set: (value: string) => {
    store.query = value
    store.resetPage()
  },
})

// Depth scopes are a key set on the field and three flags in the store; the adapter is in `search.ts`.
const scopes = computed(() => taskSearchScopes((scope) => t(`tasks.task.filter.scope.${scope}`)))
const activeScopes = taskScopesModel(
  () => store.searchScopes,
  (next) => {
    store.searchScopes = next
    store.resetPage()
  },
)

const statusPicked = computed({
  get: () => store.statusFilter,
  set: (value: string[]) => {
    store.statusFilter = value
    store.resetPage()
  },
})

/** Priority is picked one at a time: a cleared value (`null`) means "all", and paging resets to the first. */
function pickPriority(value: string | null) {
  store.priorityFilter = value
  store.resetPage()
}

/**
 * The "show beyond the usual" group: a pressed button — shown, released — hidden.
 *
 * In the store these are two flags of opposite polarity: `hideFinished` (default — hide) and
 * `includeDeleted` (default — do not ask the backend). The polarity is inverted here because on
 * screen both buttons answer one question — "is this shown right now?" — and a "don't hide
 * finished" button would read backwards.
 */
const extras = computed({
  get: () => [
    ...(store.hideFinished ? [] : [EXTRA_FINISHED]),
    ...(store.includeDeleted ? [EXTRA_DELETED] : []),
  ],
  set: (keys: string[]) => {
    store.hideFinished = !keys.includes(EXTRA_FINISHED)
    store.resetPage()
    // The trash is the only control that costs a new request: the normal response has no deleted
    // tasks at all, and there is no way to show them other than asking the backend again.
    const deleted = keys.includes(EXTRA_DELETED)
    if (deleted !== store.includeDeleted) void store.showDeleted(deleted)
  },
})

/** "Reset" — when there is something to reset: an applied filter or a changed default. */
const showReset = computed(
  () => store.hasActiveFilters || store.includeDeleted || !store.hideFinished,
)

function resetAll() {
  store.clearFilters()
  if (store.includeDeleted) void store.showDeleted(false)
}

// ── Applied ──────────────────────────────────────────────────────────────────

/**
 * The applied line answers one question — "what is narrowing it right now" — in one place, rather
 * than across several fields each of which has to be checked separately. Status values appear in
 * it one by one: they are picked as a set, and they have to be cleared one by one too.
 *
 * Finished and deleted are here too, when the list shows them: they change what is on screen as
 * much as any filter, and a pressed button at the far end of the row is easy to miss — the line is
 * where a person looks to learn why the list looks the way it does. Closing the chip returns the
 * default: finished hidden again, deleted no longer asked for.
 */
const CHIP_QUERY = 'query'
const CHIP_PRIORITY = 'priority'
const CHIP_STATUS = 'status:'
const CHIP_FINISHED = 'finished'
const CHIP_DELETED = 'deleted'

const applied = computed<AppliedFilter[]>(() => {
  const out: AppliedFilter[] = []
  const needle = store.query.trim()
  if (needle) out.push({ key: CHIP_QUERY, label: needle })
  for (const status of store.statusFilter)
    out.push({ key: `${CHIP_STATUS}${status}`, label: t(`tasks.task.status.${status}`) })
  if (store.priorityFilter !== null)
    out.push({ key: CHIP_PRIORITY, label: t(`tasks.task.priority.${store.priorityFilter}`) })
  if (!store.hideFinished) out.push({ key: CHIP_FINISHED, label: t('tasks.task.filter.finished') })
  if (store.includeDeleted) out.push({ key: CHIP_DELETED, label: t('tasks.task.filter.deleted') })
  return out
})

function drop(key: string) {
  if (key === CHIP_QUERY) query.value = ''
  else if (key === CHIP_PRIORITY) pickPriority(null)
  else if (key === CHIP_FINISHED) extras.value = extras.value.filter((extra) => extra !== EXTRA_FINISHED)
  else if (key === CHIP_DELETED) extras.value = extras.value.filter((extra) => extra !== EXTRA_DELETED)
  else if (key.startsWith(CHIP_STATUS)) {
    const status = key.slice(CHIP_STATUS.length)
    statusPicked.value = store.statusFilter.filter((value) => value !== status)
  }
}
</script>

<template>
  <FilterPanel :applied="applied" :resettable="showReset" @remove="drop" @clear="resetAll">
    <SearchField
      v-model="query"
      v-model:active-scopes="activeScopes"
      :scopes="scopes"
      :placeholder="t('tasks.task.filter.query')"
      density="compact"
      class="filter-search task-filters__search"
    />

    <!-- Status is picked as a set: "in progress and in review" is a common stance, and one value
         at a time would mean looking at the list twice. The icon is the same as in the list row
         and in the status field on the detail page: one status cannot look different in three
         places. -->
    <VSelect
      v-model="statusPicked"
      :items="statusItems"
      :label="t('tasks.task.filter.status')"
      variant="outlined"
      density="compact"
      hide-details
      clearable
      multiple
      :chips="false"
      class="filter-select task-filters__pick task-filters__pick--status"
    >
      <template #item="{ props: itemProps, item }">
        <VListItem v-bind="itemProps">
          <template #prepend="{ isSelected }">
            <VCheckboxBtn :model-value="isSelected" density="compact" />
            <span class="task-filters__glyph" :class="`task-filters__glyph--${statusColor(item.value)}`">
              <component :is="statusIcon(item.value)" :size="16" :stroke-width="1.6" />
            </span>
          </template>
        </VListItem>
      </template>

      <!-- The selection is shown as icons with labels, and past a threshold as a counter: the
           whole set does not fit the field, and cut off mid-word it does not read at all.
           `:chips="false"` is mandatory here: the app enables chips on every VSelect at once
           (`plugins/vuetify.ts`), and with them Vuetify renders `#chip` and silently ignores this
           slot — the same trap as in the status field on the detail page. -->
      <template #selection="{ item, index }">
        <span v-if="index === 0" class="task-filters__picked">
          <span class="task-filters__glyph" :class="`task-filters__glyph--${statusColor(item.value)}`">
            <component :is="statusIcon(item.value)" :size="14" :stroke-width="1.6" />
          </span>
          <!-- The label is a separate element: an ellipsis works on its own block, not on a line
               of a flex container with an icon next to it. -->
          <span class="task-filters__picked-text">{{ item.title }}</span>
          <!-- The counter lives INSIDE the first selected value, not as a separate one: Vuetify
               puts each value in its own wrapper, and the second would get clipped along with the
               label — "more" without a number says nothing. Here it is the label's neighbour and
               shrinks last. -->
          <span v-if="store.statusFilter.length > 1" class="task-filters__more">
            {{ t('tasks.task.filter.status_more', { count: store.statusFilter.length - 1 }) }}
          </span>
        </span>
      </template>
    </VSelect>

    <!-- `:chips="false"` for the same reason as for status: the app enables chips on every
         VSelect (`plugins/vuetify.ts`), and a chip in the field does not shrink or ellipsize.
         The filter value should not be a chip anyway: the chips sit on the line below, and in
         the field they would be a copy of them.
         Priority is recognised by the same glyph as in the list row and in the priority field on
         the detail page — both in the items and in the selected value. -->
    <VSelect
      :model-value="store.priorityFilter"
      :items="priorityItems"
      :label="t('tasks.task.filter.priority')"
      variant="outlined"
      density="compact"
      hide-details
      clearable
      :chips="false"
      class="filter-select task-filters__pick"
      @update:model-value="pickPriority"
    >
      <template #item="{ props: itemProps, item }">
        <VListItem v-bind="itemProps">
          <template #prepend>
            <span class="task-filters__glyph" :class="`task-filters__glyph--${priorityColor(item.value)}`">
              <component :is="priorityIcon(item.value)" :size="16" :stroke-width="1.6" />
            </span>
          </template>
        </VListItem>
      </template>

      <template #selection="{ item }">
        <span class="task-filters__picked">
          <span class="task-filters__glyph" :class="`task-filters__glyph--${priorityColor(item.value)}`">
            <component :is="priorityIcon(item.value)" :size="14" :stroke-width="1.6" />
          </span>
          <span class="task-filters__picked-text">{{ item.title }}</span>
        </span>
      </template>
    </VSelect>

    <!-- Pressed button = shown. A group, not two separate switches: both answer one question,
         "what else to show", and apart they would read as two independent filters. -->
    <VBtnToggle
      v-model="extras"
      multiple
      variant="outlined"
      divided
      density="compact"
      color="primary"
      class="filter-toggles task-filters__extras"
    >
      <VBtn :value="EXTRA_FINISHED" size="small">
        <template #prepend><IconCircleCheck :size="16" :stroke-width="1.7" /></template>
        {{ t('tasks.task.filter.finished') }}
      </VBtn>
      <VBtn :value="EXTRA_DELETED" size="small">
        <template #prepend><IconTrash :size="16" :stroke-width="1.7" /></template>
        {{ t('tasks.task.filter.deleted') }}
      </VBtn>
    </VBtnToggle>
  </FilterPanel>
</template>

<style scoped>
/* Field widths come from `FilterPanel` (`filter-search` / `filter-select` / `filter-toggles`);
   here only what is inside the fields. */
.task-filters__search :deep(.v-field__input) { font-size: 13px; }
.task-filters__search :deep(.v-field__prepend-inner) { color: var(--text-faint); }

/* THE FIELD IS ALWAYS ONE LINE. Vanilla VSelect wraps the selection onto a second line and grows
   the field in height — the controls row then drifts apart vertically, and neighbouring fields no
   longer line up. A long value is cut with an ellipsis: "Unsor" cut mid-word does not read, while
   "Unsorted…" does. */
.task-filters__pick :deep(.v-field__input) {
  font-size: 13px;
  flex-wrap: nowrap;
  overflow: hidden;
}

.task-filters__pick :deep(.v-select__selection) {
  min-width: 0;
  overflow: hidden;
}

.task-filters__pick :deep(.v-select__selection-text) {
  overflow: hidden;
  white-space: nowrap;
  text-overflow: ellipsis;
}

/* The status field holds a value with an icon plus a counter of the rest: it needs to be wider
   than its single-value neighbours. Two classes to outweigh the panel's `filter-select`; on a phone
   the panel's full width wins. */
@media (min-width: 600px) {
  .filter-select.task-filters__pick--status { flex: 0 1 200px; min-width: 176px; }
}

.task-filters__extras :deep(.v-btn) { font-size: 12px; }

/* The selected status in the field: icon and label on one line. A long label shrinks into an
   ellipsis, but the counter after it is not lost — it says more than this one is selected. */
.task-filters__picked {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  min-width: 0;
  margin-inline-end: 6px;
  font-size: 13px;
}

.task-filters__picked-text {
  min-width: 0;
  overflow: hidden;
  white-space: nowrap;
  text-overflow: ellipsis;
}

.task-filters__more {
  flex: none;
  font-size: 12px;
  color: var(--text-faint);
}

/* Same colors as the glyph in the list row and in the status field on the detail page. */
.task-filters__glyph {
  display: inline-flex;
  align-items: center;
  flex: none;
}

.task-filters__glyph--accent  { color: var(--accent); }
.task-filters__glyph--success { color: var(--success); }
.task-filters__glyph--error   { color: var(--error); }
.task-filters__glyph--warn    { color: var(--warn); }
.task-filters__glyph--muted   { color: var(--text-faint); }
</style>
