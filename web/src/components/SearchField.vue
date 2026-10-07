<script lang="ts">
import type { TablerIcon } from '@/shared/nav'

/**
 * One toggleable search scope: `key` goes out into the model, `icon` is drawn on the button,
 * `label` is the tooltip (as text, because the button carries nothing but a glyph).
 */
export type SearchScope = {
  key: string
  icon: TablerIcon
  label: string
}
</script>

<script setup lang="ts">
// A search field with scope toggles right inside its frame: one query string, and the buttons say
// WHERE to search it. The toggles live in the field rather than next to it because they belong to
// this query and nothing else — moved out into a panel, they would read as a second filter.
//
// Model split: `v-model` is the text, `v-model:active-scopes` the keys of enabled scopes (the
// `scopes` prop describes the set itself, so the enabled ones get a separate name). Both models
// change independently (scopes are toggled even with an empty field), and the consumer decides
// whether to re-query: switching scope with an empty query changes nothing in the results.
import { IconSearch } from '@tabler/icons-vue'

withDefaults(defineProps<{
  /** Scope toggles; an empty set gives a plain search field without buttons. */
  scopes?: SearchScope[]
  label?: string
  placeholder?: string
  /**
   * An explanation under the field — e.g. what exactly the haystack includes with the enabled
   * scopes. It always stays in place: it describes the current search scope rather than hinting
   * while typing, and appearing on focus would jolt the panel layout.
   */
  hint?: string
  density?: 'default' | 'comfortable' | 'compact'
  clearable?: boolean
}>(), {
  scopes: () => [],
  density: 'comfortable',
  clearable: true,
})

const query = defineModel<string>({ default: '' })
const activeScopes = defineModel<string[]>('activeScopes', { default: () => [] })

// VTextField's clear × emits `null`, while a string is promised outward: the consumer calls
// `trim()` on the query and would crash on an empty field. An empty string means the same "nothing entered".
function setQuery(value: string | null) {
  query.value = value ?? ''
}

function isActive(key: string): boolean {
  return activeScopes.value.includes(key)
}

// A new array, not an in-place mutation: the consumer's watchers track the reference.
function toggle(key: string) {
  activeScopes.value = isActive(key)
    ? activeScopes.value.filter((active) => active !== key)
    : [...activeScopes.value, key]
}
</script>

<template>
  <VTextField
    :model-value="query"
    :label="label"
    :placeholder="placeholder"
    :prepend-inner-icon="IconSearch"
    :density="density"
    :clearable="clearable"
    :hint="hint"
    :persistent-hint="!!hint"
    :hide-details="!hint"
    variant="outlined"
    class="search-field"
    @update:model-value="setQuery"
  >
    <template v-if="scopes.length" #append-inner>
      <!-- mousedown is suppressed, otherwise pressing a button takes the caret out of the field: the
           user clicks a toggle in the middle of typing a query and keeps typing. -->
      <div class="search-field__scopes" @mousedown.prevent>
        <VDivider vertical class="search-field__divider" />
        <VBtn
          v-for="scope in scopes"
          :key="scope.key"
          :color="isActive(scope.key) ? 'primary' : undefined"
          :variant="isActive(scope.key) ? 'tonal' : 'text'"
          :aria-label="scope.label"
          :aria-pressed="isActive(scope.key)"
          size="x-small"
          icon
          density="comfortable"
          @click="toggle(scope.key)"
        >
          <component :is="scope.icon" :size="16" :stroke-width="1.7" />
          <VTooltip activator="parent" location="top">{{ scope.label }}</VTooltip>
        </VBtn>
      </div>
    </template>
  </VTextField>
</template>

<style scoped>
.search-field__scopes {
  display: flex;
  align-items: center;
  gap: 2px;
  margin-inline-start: 2px;
}

/* The rule sets the toggles apart from the text: without it the glyphs read as part of the query. */
.search-field__divider {
  margin-inline-end: 4px;
  height: 20px;
  align-self: center;
}
</style>
