<script setup lang="ts">
// The available codexes toolbar — the workspaces and groups toolbars' anatomy in the shared
// `FilterPanel` frame: a search over the name, code and description, and the deleted ones. The
// values live in the list store, so the search survives leaving the page.
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { IconTrash } from '@tabler/icons-vue'

import FilterPanel, { type AppliedFilter } from '@/components/FilterPanel.vue'
import SearchField from '@/components/SearchField.vue'

import { useCodexListStore } from '../stores/codex-list.store'

const { t } = useI18n()
const store = useCodexListStore()

const DELETED = 'deleted'

const extras = computed({
  get: () => (store.showDeleted ? [DELETED] : []),
  set: (keys: string[]) => {
    store.showDeleted = keys.includes(DELETED)
  },
})

const applied = computed<AppliedFilter[]>(() => {
  const out: AppliedFilter[] = []
  const needle = store.query.trim()
  if (needle) out.push({ key: 'query', label: needle })
  if (store.showDeleted) out.push({ key: DELETED, label: t('codex.filter.deleted') })
  return out
})

const total = computed(() => t('codex.filter.total', { shown: store.visible.length, all: store.items.length }))

function drop(key: string) {
  if (key === 'query') store.query = ''
  else store.showDeleted = false
}

function resetAll() {
  store.query = ''
  store.showDeleted = false
}
</script>

<template>
  <FilterPanel
    :applied="applied"
    :resettable="applied.length > 0"
    :total="applied.length ? total : undefined"
    @remove="drop"
    @clear="resetAll"
  >
    <SearchField
      v-model="store.query"
      :placeholder="t('codex.filter.query')"
      density="compact"
      class="filter-search codex-filters__search"
    />

    <VBtnToggle
      v-model="extras"
      multiple
      variant="outlined"
      divided
      density="compact"
      color="primary"
      class="filter-toggles codex-filters__extras"
    >
      <VBtn :value="DELETED" size="small">
        <template #prepend><IconTrash :size="16" :stroke-width="1.7" /></template>
        {{ t('codex.filter.deleted') }}
      </VBtn>
    </VBtnToggle>
  </FilterPanel>
</template>

<style scoped>
.codex-filters__search :deep(.v-field__input) { font-size: 13px; }
.codex-filters__search :deep(.v-field__prepend-inner) { color: var(--text-faint); }

.codex-filters__extras :deep(.v-btn) { font-size: 12px; }
</style>
