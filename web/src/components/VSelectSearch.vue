<script setup lang="ts">
/**
 * VSelect with a search row pinned atop the open menu.
 *
 * Vuetify has no built-in for this — VAutocomplete merges the query into the field,
 * which changes the field display. VSelectSearch keeps the field untouched and filters
 * the items in place via the #prepend-item slot. All VSelect props/slots pass through
 * ($attrs + slot forwarding), so it's a drop-in replacement: swap VSelect → VSelectSearch.
 */
import { computed, ref, useSlots } from 'vue'
import { useI18n } from 'vue-i18n'
import { IconSearch } from '@tabler/icons-vue'

const model = defineModel<unknown>()

const props = withDefaults(defineProps<{
  items: unknown[]
  /** Property read as the display title for object items (mirrors VSelect's item-title). */
  itemTitle?: string
  /** Property read as the value of object items (mirrors VSelect's item-value). */
  itemValue?: string
  /** The model holds whole items rather than their values (mirrors VSelect's return-object). */
  returnObject?: boolean
  /** Placeholder for the in-dropdown search field. */
  searchPlaceholder?: string
  /** Text shown when the filter matches nothing. */
  noDataText?: string
}>(), {
  itemTitle: 'title',
  itemValue: 'value',
  returnObject: false,
})

const { t } = useI18n()

defineOptions({ inheritAttrs: false })

const search = ref('')

function titleOf(item: unknown): string {
  if (item != null && typeof item === 'object') {
    return String((item as Record<string, unknown>)[props.itemTitle] ?? '')
  }
  return String(item ?? '')
}

const filtered = computed(() => {
  const q = search.value.trim().toLowerCase()
  if (!q) return props.items
  return props.items.filter(it => titleOf(it).toLowerCase().includes(q))
})

function valueOf(item: unknown): unknown {
  if (item != null && typeof item === 'object') {
    return (item as Record<string, unknown>)[props.itemValue]
  }
  return item
}

function itemFor(value: unknown): unknown {
  if (value == null) return value
  return props.items.find(it => valueOf(it) === value) ?? value
}

// VSelect is always fed whole items, and the model is mapped to them here. Given a bare value,
// VSelect looks its item up in the list it was handed — the filtered one — so a query that hides
// the selection would leave the field with a value it can no longer title. A whole item carries
// its own title and is shown as is.
const selection = computed(() => {
  if (props.returnObject) return model.value
  return Array.isArray(model.value) ? model.value.map(itemFor) : itemFor(model.value)
})

function onSelect(picked: unknown) {
  if (props.returnObject) model.value = picked
  else model.value = Array.isArray(picked) ? picked.map(valueOf) : picked == null ? picked : valueOf(picked)
}

// Clear the query when the menu closes so it reopens clean.
function onMenuToggle(open: boolean) {
  if (!open) search.value = ''
}

// Forward every consumer slot to VSelect except the two we own (prepend-item / no-data).
const slots = useSlots()
const forwardedSlots = computed(() =>
  Object.keys(slots).filter(name => name !== 'prepend-item' && name !== 'no-data'),
)
</script>

<template>
  <VSelect
    v-bind="$attrs"
    :model-value="selection"
    :items="filtered"
    :item-title="itemTitle"
    :item-value="itemValue"
    return-object
    @update:model-value="onSelect"
    @update:menu="onMenuToggle"
  >
    <template #prepend-item>
      <div class="vss-search">
        <VTextField
          v-model="search"
          :prepend-inner-icon="IconSearch"
          :placeholder="searchPlaceholder ?? t('common.prefs.search')"
          variant="plain"
          density="compact"
          autofocus
          hide-details
          @keydown.stop
        />
      </div>
      <VDivider class="vss-divider" />
    </template>

    <template #no-data>
      <div class="vss-empty">{{ noDataText ?? t('common.prefs.not_found') }}</div>
    </template>

    <template v-for="name in forwardedSlots" #[name]="slotProps" :key="name">
      <slot :name="name" v-bind="slotProps ?? {}" />
    </template>
  </VSelect>
</template>

<style scoped>
/* Search row + empty state live in the teleported menu — scope id still reaches them. */
.vss-search {
  padding: 4px 10px 6px;
}

/* Spacing under the rule: otherwise the first item's hover highlight sits flush against it, and the
   rule reads as the item's edge rather than the search row's boundary. */
.vss-divider {
  margin-bottom: 4px;
}

.vss-empty {
  padding: 10px 16px;
  font-size: 13px;
  color: var(--text-faint);
}
</style>
