<script setup lang="ts">
/**
 * VSelect with a search row pinned atop the open menu.
 *
 * Vuetify has no built-in for this — VAutocomplete merges the query into the field,
 * which changes the field display. VSelectSearch keeps the field untouched and filters
 * the items in place via the #prepend-item slot. All VSelect props/slots pass through
 * ($attrs + slot forwarding), so it's a drop-in replacement: swap VSelect → VSelectSearch.
 */
import { computed, nextTick, ref, useAttrs, useSlots, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { IconSearch } from '@tabler/icons-vue'
import type { VSelect } from 'vuetify/components'

type MenuProps = InstanceType<typeof VSelect>['$props']['menuProps']

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
  /** What the query is matched against; the title by default. For items known by more than
   *  their title — a language found by `js` as well as by `javascript`. */
  itemSearch?: (item: unknown) => string
  /** Order matches by how well they match — a whole word first, then a word's start, then
   *  anywhere — instead of keeping the list's order. For long lists of short names, where `ts`
   *  would otherwise bury `typescript` under `kotlin` and `systemd`. */
  ranked?: boolean
}>(), {
  itemTitle: 'title',
  itemValue: 'value',
  returnObject: false,
  ranked: false,
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
  const searchable = props.itemSearch ?? titleOf
  const matches = props.items.filter(it => searchable(it).toLowerCase().includes(q))
  if (!props.ranked) return matches
  const rank = (item: unknown): number => {
    const words = searchable(item).toLowerCase().split(/\s+/)
    if (words.includes(q)) return 0
    return words.some(word => word.startsWith(q)) ? 1 : 2
  }
  // Array.sort is stable, so items of one rank keep the list's own order.
  return matches.map(item => ({ item, rank: rank(item) }))
    .sort((a, b) => a.rank - b.rank)
    .map(entry => entry.item)
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

const menuOpen = ref(false)

function onMenuToggle(open: boolean) {
  menuOpen.value = open
}

// Clear the query when the menu closes so it reopens clean. Watched on the state, not in the
// toggle event: Enter and Escape close the menu from here, and VSelect emits nothing for a change
// it did not make — the old query then came back prefixed to the next one.
watch(menuOpen, (open) => {
  if (!open) search.value = ''
})

// The search field keeps its keys from VSelect — a letter must not reach the first-letter lookup
// — so the keys that drive the menu are handled here instead: ↓ steps into the list (VList moves
// on from there), Enter takes the first match, Escape closes. Without these the open menu was a
// keyboard trap: focus sits in the field, and nothing typed there could pick or leave.
function onSearchKeydown(event: KeyboardEvent) {
  event.stopPropagation()
  if (event.key === 'Escape') {
    menuOpen.value = false
  } else if (event.key === 'ArrowDown') {
    event.preventDefault()
    const list = (event.target as HTMLElement).closest('.v-list')
    list?.querySelector<HTMLElement>('.v-list-item:not(.v-list-item--disabled)')?.focus()
  } else if (event.key === 'Enter') {
    event.preventDefault()
    pickFirst()
  }
}

function pickFirst() {
  const multiple = attrs.multiple !== undefined && attrs.multiple !== false
  const first = filtered.value[0]
  if (multiple || first === undefined) return
  onSelect(first)
  menuOpen.value = false
}

const isPrintable = (event: KeyboardEvent): boolean =>
  event.key.length === 1 && !event.ctrlKey && !event.metaKey && !event.altKey

// Between a click on the field and the search row taking focus the menu is still opening, and the
// field itself holds focus. Letters typed in that window went to VSelect's first-letter lookup:
// `ts` + Enter picked `ts-tags` and left the menu open. Caught on the way down, before VSelect
// sees them, they become the query instead — and Enter on a query takes its first match, as it
// does in the search row.
function onFieldKeydown(event: KeyboardEvent) {
  if (isPrintable(event)) {
    event.preventDefault()
    event.stopPropagation()
    search.value += event.key
    menuOpen.value = true
    nextTick(() => searchField.value?.focus())
  } else if (event.key === 'Enter' && menuOpen.value && search.value) {
    event.preventDefault()
    event.stopPropagation()
    pickFirst()
  }
}

// VSelect moves focus to the selected item once the menu has finished opening (`onAfterEnter`),
// taking it from the search field `autofocus` put it in. Typed letters then went to VSelect's
// first-letter lookup, which picks an item and closes the menu — with a value already chosen,
// opening the list and typing a query silently changed it. Vuetify merges the menu's handlers
// with its own and runs ours after, so focus is handed back here.
const searchField = ref<{ focus: () => void } | null>(null)
const attrs = useAttrs()

// The listener is not in VMenu's declared props, only in what Vue forwards to it — hence the cast.
const menuProps = computed((): MenuProps => {
  const own = (attrs.menuProps ?? attrs['menu-props'] ?? {}) as Record<string, unknown>
  const consumerAfterEnter = own.onAfterEnter as (() => void) | undefined
  return {
    ...own,
    onAfterEnter: () => {
      searchField.value?.focus()
      consumerAfterEnter?.()
    },
  } as MenuProps
})

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
    :menu-props="menuProps"
    :menu="menuOpen"
    @keydown.capture="onFieldKeydown"
    @update:model-value="onSelect"
    @update:menu="onMenuToggle"
  >
    <template #prepend-item>
      <div class="vss-search">
        <VTextField
          ref="searchField"
          v-model="search"
          :prepend-inner-icon="IconSearch"
          :placeholder="searchPlaceholder ?? t('common.prefs.search')"
          variant="plain"
          density="compact"
          autofocus
          hide-details
          @keydown="onSearchKeydown"
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
