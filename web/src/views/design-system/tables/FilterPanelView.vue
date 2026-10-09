<script setup lang="ts">
// The filter panel showcase: `ListFilters` on a `useListFilters` schema — the same pair a list page
// uses. There are no requests: the state lives in the composable and is written to this page's
// address, and a change counter stands in for the reload.
import { computed, ref } from 'vue'
import { useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { IconCircleCheck, IconTrash } from '@tabler/icons-vue'

import PageLayout from '@/layout/templates/PageLayout.vue'
import PageHeader from '@/layout/components/PageHeader.vue'
import FilterPanel, { type AppliedFilter } from '@/components/FilterPanel.vue'
import ListFilters from '@/components/ListFilters.vue'
import SearchField from '@/components/SearchField.vue'
import CodeBlock from '@/components/CodeBlock.vue'
import { useListFilters, type ListFilterDef } from '@/composables/useListFilters'

const { t } = useI18n()
const router = useRouter()

const schema = computed<ListFilterDef[]>(() => [
  { kind: 'search', key: 'q', label: t('design-system.section.filter-panel.sample.search') },
  {
    kind: 'select',
    key: 'status',
    label: t('design-system.section.filter-panel.sample.status'),
    options: [
      { title: t('design-system.section.filter-panel.sample.status_open'), value: 'open' },
      { title: t('design-system.section.filter-panel.sample.status_review'), value: 'review' },
      { title: t('design-system.section.filter-panel.sample.status_done'), value: 'done' },
    ],
  },
  {
    kind: 'select',
    key: 'priority',
    label: t('design-system.section.filter-panel.sample.priority'),
    options: [
      { title: t('design-system.section.filter-panel.sample.priority_high'), value: 'high' },
      { title: t('design-system.section.filter-panel.sample.priority_low'), value: 'low' },
    ],
    // Priority means nothing for finished work: the field is dimmed while status is "Done".
    disabledWhen: (filters) => filters.select('status') === 'done',
  },
  { kind: 'toggle', key: 'finished', label: t('design-system.section.filter-panel.sample.finished'), icon: IconCircleCheck },
  { kind: 'toggle', key: 'deleted', label: t('design-system.section.filter-panel.sample.deleted'), icon: IconTrash },
])

const changes = ref(0)

const filters = useListFilters(schema, () => {
  changes.value++
  void router.replace({ query: filters.toQuery() })
})

// The bare panel: the page brings its own controls and keeps the applied list itself.
const bareQuery = ref('')
const bareApplied = computed<AppliedFilter[]>(() =>
  bareQuery.value.trim() ? [{ key: 'q', label: bareQuery.value.trim() }] : [],
)

// `<\/script>` / `<\/template>` are escaped so they don't close this SFC's blocks.
const usageCode = `<script setup lang="ts">
import ListFilters from '@/components/ListFilters.vue'
import { useListFilters, type ListFilterDef } from '@/composables/useListFilters'

const schema = computed<ListFilterDef[]>(() => [
  { kind: 'search', key: 'q', label: t('tasks.filter.query') },
  { kind: 'select', key: 'status', label: t('tasks.filter.status'), options: STATUS_OPTIONS.value },
  { kind: 'toggle', key: 'deleted', label: t('tasks.filter.deleted'), icon: IconTrash },
])

// A key is the address parameter and the request parameter; any change goes back to page one
const filters = useListFilters(schema, () => { page.value = 1; void load() })
<\/script>

<template>
  <ListFilters :filters="filters" :disabled="loading" :total="t('tasks.total', { count })" />
<\/template>`

const bareCode = `<FilterPanel :applied="applied" @remove="drop" @clear="resetAll">
  <SearchField v-model="query" density="compact" class="filter-search" />
  <VSelect v-model="kind" :items="kinds" :chips="false" density="compact" hide-details class="filter-select" />
</FilterPanel>`
</script>

<template>
  <PageLayout>
  <div class="ds-page">
    <PageHeader
      :title="t('design-system.page.filter-panel.title')"
      :description="t('design-system.page.filter-panel.description')"
      back-to="/design-system"
    />

    <!-- Live -->
    <section class="ds-section">
      <h6 class="mb-3">{{ t('design-system.section.filter-panel.live') }}</h6>

      <ListFilters :filters="filters" :total="t('design-system.section.filter-panel.sample.total')" />

      <div class="ds-out">
        <span class="ds-tag">toQuery()</span>
        <code>{{ JSON.stringify(filters.toQuery()) }}</code>
        <span class="ds-tag">onChange</span>
        <code>{{ changes }}</code>
      </div>

      <p class="ds-note">{{ t('design-system.section.filter-panel.applied_note') }}</p>
      <p class="ds-note">{{ t('design-system.section.filter-panel.layout_note') }}</p>
    </section>

    <!-- Bare panel -->
    <section class="ds-section">
      <h6 class="mb-1">{{ t('design-system.section.filter-panel.bare') }}</h6>
      <p class="ds-note ds-note--lead">{{ t('design-system.section.filter-panel.bare_note') }}</p>

      <FilterPanel :applied="bareApplied" @remove="bareQuery = ''" @clear="bareQuery = ''">
        <SearchField
          v-model="bareQuery"
          :placeholder="t('design-system.section.filter-panel.sample.search')"
          density="compact"
          class="filter-search"
        />
      </FilterPanel>
      <CodeBlock :code="bareCode" lang="vue" class="mt-3" />
    </section>

    <!-- Usage -->
    <section class="ds-section">
      <h6 class="mb-3">{{ t('design-system.section.filter-panel.usage') }}</h6>
      <CodeBlock :code="usageCode" lang="vue" />
    </section>
  </div>
  </PageLayout>
</template>

<style scoped>
.ds-page { max-width: 960px; }
.ds-section { margin-bottom: 28px; }

.ds-note {
  margin: 10px 0 0;
  font-size: 13px;
  line-height: 1.5;
  color: var(--text-muted);
}

.ds-note--lead { margin: 0 0 12px; }

.ds-out {
  display: grid;
  grid-template-columns: 100px minmax(0, 1fr);
  gap: 4px 12px;
  align-items: baseline;
  margin-top: 10px;
  font-size: 12px;
}

.ds-out code { overflow-wrap: anywhere; }

.ds-tag {
  font-family: var(--font-mono);
  font-size: 11px;
  color: var(--text-faint);
}
</style>
