<script setup lang="ts">
// Workspaces toolbar: search and "show beyond the usual" — the groups toolbar (`GroupFilters`) one
// level up, in the same shared `FilterPanel` frame. A workspace has nothing but a name and a
// description, so the search has no depth scopes either.
//
// The values live in the section store, not here: the search survives leaving the page and coming
// back.
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { IconTrash } from '@tabler/icons-vue'

import FilterPanel, { type AppliedFilter } from '@/components/FilterPanel.vue'
import SearchField from '@/components/SearchField.vue'

import { useWorkspacesStore } from '../stores/workspaces.store'

const { t } = useI18n()
const store = useWorkspacesStore()

const EXTRA_DELETED = 'deleted'
const CHIP_QUERY = 'query'
const CHIP_DELETED = 'deleted'

/** Pressed button = shown. The trash costs a new request: the normal response has no deleted. */
const extras = computed({
  get: () => (store.includeDeleted ? [EXTRA_DELETED] : []),
  set: (keys: string[]) => {
    const deleted = keys.includes(EXTRA_DELETED)
    if (deleted !== store.includeDeleted) void store.showDeleted(deleted)
  },
})

// "Deleted" gets a chip while shown: the line under the controls is where a person looks to learn
// what the list is showing, and a pressed button alone is easy to miss.
const applied = computed<AppliedFilter[]>(() => {
  const out: AppliedFilter[] = []
  const needle = store.query.trim()
  if (needle) out.push({ key: CHIP_QUERY, label: needle })
  if (store.includeDeleted) out.push({ key: CHIP_DELETED, label: t('workspace.filter.deleted') })
  return out
})

const showReset = computed(() => applied.value.length > 0)

function drop(key: string) {
  if (key === CHIP_QUERY) store.query = ''
  else if (key === CHIP_DELETED) extras.value = []
}

function resetAll() {
  store.query = ''
  if (store.includeDeleted) void store.showDeleted(false)
}
</script>

<template>
  <FilterPanel :applied="applied" :resettable="showReset" @remove="drop" @clear="resetAll">
    <SearchField
      v-model="store.query"
      :placeholder="t('workspace.filter.query')"
      density="compact"
      class="filter-search workspace-filters__search"
    />

    <!-- A one-button group, not a switch: "Deleted" looks the same in the tasks and groups
         toolbars, and one toggle must not look different on neighbouring pages. -->
    <VBtnToggle
      v-model="extras"
      multiple
      variant="outlined"
      divided
      density="compact"
      color="primary"
      class="filter-toggles workspace-filters__extras"
    >
      <VBtn :value="EXTRA_DELETED" size="small">
        <template #prepend><IconTrash :size="16" :stroke-width="1.7" /></template>
        {{ t('workspace.filter.deleted') }}
      </VBtn>
    </VBtnToggle>
  </FilterPanel>
</template>

<style scoped>
/* Field widths come from `FilterPanel`; here only what is inside the fields. */
.workspace-filters__search :deep(.v-field__input) { font-size: 13px; }
.workspace-filters__search :deep(.v-field__prepend-inner) { color: var(--text-faint); }

.workspace-filters__extras :deep(.v-btn) { font-size: 12px; }
</style>
