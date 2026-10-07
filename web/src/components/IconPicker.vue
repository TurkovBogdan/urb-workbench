<script setup lang="ts">
// Icon choice from a fixed set: a grey panel with a search field and scrolling tiles inside.
//
// The set comes as a prop rather than from a registry: the component is shared, and there may be
// several registries (today — the research shelf palette). The name-to-component resolver is a prop
// for the same reason — a runtime lookup across all of @tabler/icons-vue would drag ~6000
// components into the bundle.
//
// Search is BY CODE (`building-factory-2`), not by translation: the code is what goes to the
// database, searching by it is unambiguous, and a second 120-line dictionary isn't needed. The code
// itself isn't printed: the person picks a picture, not a string, and the selection shows by the
// tile highlight.
import { computed, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { IconSearch } from '@tabler/icons-vue'
import type { TablerIcon } from '@/shared/nav'

const props = withDefaults(defineProps<{
  /** The selected icon code; `null` — nothing selected. */
  modelValue?: string | null
  /** The full set of codes in display order. */
  icons: string[]
  /** Code → component. The resolver must cover an unknown code itself (with a fallback icon). */
  resolve: (name: string) => TablerIcon
  /** Height of the tile area; beyond it the area scrolls. The search stays in place. */
  height?: number | string
  /** Drop the tray: the panel is drawn by whoever nests the picker in theirs (see IconColorPicker). */
  bare?: boolean
}>(), {
  modelValue: null,
  height: 220,
  bare: false,
})

const emit = defineEmits<{ 'update:modelValue': [string] }>()

const { t } = useI18n()

const query = ref('')

const visible = computed(() => {
  const needle = query.value.trim().toLowerCase()
  return needle ? props.icons.filter(name => name.includes(needle)) : props.icons
})

const scrollHeight = computed(() => (
  typeof props.height === 'number' ? `${props.height}px` : props.height
))
</script>

<template>
  <div
    class="icon-picker"
    :class="{ 'icon-picker--bare': props.bare }"
    :style="{ '--picker-height': scrollHeight }"
  >
    <div class="icon-picker__search">
      <VTextField
        v-model="query"
        :placeholder="t('common.icon_picker.search')"
        :prepend-inner-icon="IconSearch"
        variant="outlined"
        density="compact"
        hide-details
        clearable
      />
    </div>

    <div class="icon-picker__rule" />

    <div class="icon-picker__scroll">
      <p v-if="visible.length === 0" class="icon-picker__empty">
        {{ t('common.icon_picker.empty', { query: query.trim() }) }}
      </p>

      <div v-else class="icon-picker__grid">
        <button
          v-for="name in visible"
          :key="name"
          type="button"
          class="icon-picker__tile"
          :class="{ 'icon-picker__tile--active': name === props.modelValue }"
          :title="name"
          :aria-label="name"
          :aria-pressed="name === props.modelValue"
          @click="emit('update:modelValue', name)"
        >
          <component :is="props.resolve(name)" :size="20" :stroke-width="1.6" />
        </button>
      </div>
    </div>
  </div>
</template>

<style scoped>
/* The panel is a sunken tray (the `--surface-sunken` role, like kanban columns): tiles on it read as
   lying on top. Inside are three bands: search, divider, scroll area. The search and the rule are
   pinned; only the tiles scroll. */
.icon-picker {
  display: flex;
  flex-direction: column;
  border-radius: 10px;
  background: var(--surface-sunken);
  border: 1px solid var(--border-sunken);
  overflow: hidden;
}

/* Without the tray only the bands remain: whoever nested the picker draws a tray around the whole
   set, and a second background with a border inside would read as a window within a window. */
.icon-picker--bare {
  background: none;
  border: none;
  border-radius: 0;
}

.icon-picker__search {
  padding: 10px;
}

.icon-picker__search :deep(.v-field) {
  background: var(--surface);
}

/* The rule spans the full tray width, not the padded area: it separates the search band from the
   content — the same role as the rule under a window header. So the paddings live in the bands, not on the panel. */
.icon-picker__rule {
  height: 1px;
  background: var(--border);
}

.icon-picker__scroll {
  max-height: var(--picker-height);
  overflow-y: auto;
  padding: 10px;
}

.icon-picker__grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(40px, 1fr));
  gap: 6px;
}

.icon-picker__tile {
  display: flex;
  align-items: center;
  justify-content: center;
  height: 40px;
  border-radius: 8px;
  color: var(--text-muted);
  background: var(--surface);
  border: 1px solid var(--border-soft);
  cursor: pointer;
  transition: color 120ms ease, background-color 120ms ease, border-color 120ms ease;
}

.icon-picker__tile:hover {
  color: var(--text);
  border-color: var(--border);
}

.icon-picker__tile:focus-visible {
  outline: 2px solid var(--accent);
  outline-offset: 1px;
}

/* The selected tile is painted with the accent — OR with the color, if the picker is nested in a
   panel where a color is already chosen (`.color-tones` on an ancestor supplies the roles). Variable
   inheritance is the link between the two choices: no separate prop is needed for it. */
.icon-picker__tile--active,
.icon-picker__tile--active:hover {
  color: var(--gc-ink, var(--accent));
  background: var(--gc-fill, var(--accent-soft));
  border-color: var(--gc-ink, var(--accent));
}

.icon-picker__empty {
  margin: 0;
  padding: 18px 4px;
  text-align: center;
  font-size: 12px;
  color: var(--text-muted);
}
</style>
