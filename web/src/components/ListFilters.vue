<script setup lang="ts">
// A filter panel built from a `useListFilters` schema: the page describes its filters, and the
// fields, chips and reset come from here. Order in the row: search and selects as in the schema,
// then whatever the page puts into the slot, then the toggles as one group at the right edge.
import { computed } from 'vue'

import FilterPanel from '@/components/FilterPanel.vue'
import SearchField from '@/components/SearchField.vue'
import type { ListFilterDef, ListFilters } from '@/composables/useListFilters'

const props = withDefaults(defineProps<{
  filters: ListFilters
  /** The first load: fields are dimmed while there is nothing to filter yet. */
  disabled?: boolean
  /** The result of the filter at the right edge ("42 tasks"). */
  total?: string
}>(), {
  disabled: false,
  total: undefined,
})

type ToggleDef = Extract<ListFilterDef, { kind: 'toggle' }>

const fields = computed(() => props.filters.defs.value.filter((def) => def.kind !== 'toggle'))

const toggles = computed(() =>
  props.filters.defs.value.filter((def): def is ToggleDef => def.kind === 'toggle'),
)

const pressed = computed(() =>
  toggles.value.filter((def) => props.filters.flag(def.key)).map((def) => def.key),
)

function isDisabled(def: ListFilterDef): boolean {
  return props.disabled || (def.disabledWhen?.(props.filters) ?? false)
}

// The group hands over the whole pressed set — apply only the button that changed.
function onToggle(value: string[]): void {
  for (const def of toggles.value) {
    const on = value.includes(def.key)
    if (on !== props.filters.flag(def.key)) props.filters.set(def.key, on)
  }
}
</script>

<template>
  <FilterPanel
    :applied="filters.applied.value"
    :resettable="filters.resettable.value"
    :total="total"
    @remove="filters.remove"
    @clear="filters.clear"
  >
    <template v-for="def in fields" :key="def.key">
      <SearchField
        v-if="def.kind === 'search'"
        :model-value="filters.input(def.key)"
        :placeholder="def.label"
        density="compact"
        :disabled="isDisabled(def)"
        class="filter-search"
        @update:model-value="filters.set(def.key, $event)"
      />
      <!-- `:chips="false"`: the app enables chips on every VSelect (`plugins/vuetify.ts`), and a
           chip in the field neither shrinks nor ellipsizes. The value is a chip on the line below
           anyway. `item-props` lets an option carry its `subtitle` as a second line. -->
      <VSelect
        v-else-if="def.kind === 'select'"
        :model-value="filters.select(def.key)"
        :items="def.options"
        item-props
        item-title="title"
        item-value="value"
        :label="def.label"
        variant="outlined"
        density="compact"
        hide-details
        clearable
        :chips="false"
        :disabled="isDisabled(def)"
        class="filter-select"
        @update:model-value="filters.set(def.key, $event ?? null)"
      />
    </template>

    <!-- Page-specific fields stand between the selects and the toggles. -->
    <slot />

    <VBtnToggle
      v-if="toggles.length > 0"
      :model-value="pressed"
      multiple
      variant="outlined"
      density="compact"
      divided
      color="primary"
      :disabled="disabled"
      class="filter-toggles"
      @update:model-value="onToggle"
    >
      <VBtn v-for="def in toggles" :key="def.key" :value="def.key" size="small" :disabled="isDisabled(def)">
        <template #prepend><component :is="def.icon" :size="16" :stroke-width="1.7" /></template>
        {{ def.label }}
      </VBtn>
    </VBtnToggle>
  </FilterPanel>
</template>

<style scoped>
.filter-search :deep(.v-field__input),
.filter-select :deep(.v-field__input) { font-size: 13px; }
.filter-search :deep(.v-field__prepend-inner) { color: var(--text-faint); }
.filter-toggles :deep(.v-btn) { font-size: 12px; }
</style>
