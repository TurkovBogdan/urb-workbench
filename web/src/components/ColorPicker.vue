<script setup lang="ts">
// Color choice from a fixed set: a tray of tiles, one tile — one named color.
//
// The set and the resolver come as props for the same reason as in IconPicker: the component is
// shared, and there may be several registries (today — the research shelf palette). The resolver
// returns color steps as variables, the tile is painted with the `--gc-swatch` role, and which step
// is readable in the current theme is decided by `.color-tones` in main.scss — the picker knows
// nothing about themes (see shared/colorTones.ts).
//
// What goes in and out is the NAME (`blue`), not a hex: the name is what goes to the database.
// There's no point printing it on the tile (the person picks a color, not a string), so it lives
// in the tooltip and `aria-label`, and the selection shows by the check alone.
//
// A check rather than a ring: the whole set consists of colors, and a state shown by color would
// get lost in it, while a dark ring around one tile outweighs the color it marks.
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { IconCheck } from '@tabler/icons-vue'
import type { ColorToneVars } from '@/shared/colorTones'

const props = withDefaults(defineProps<{
  /** The selected color name; `null` — no color set. */
  modelValue?: string | null
  /** The full set of names in display order. */
  colors: string[]
  /** Name → color steps as variables. The resolver must cover an unknown name itself. */
  resolve: (name: string) => ColorToneVars
  /** Show a "no color" tile; choosing it emits `null`. */
  clearable?: boolean
  /** Tile side in pixels; the column count derives from it. */
  size?: number
  /** Drop the tray: the panel is drawn by whoever nests the picker in theirs (see IconColorPicker). */
  bare?: boolean
}>(), {
  modelValue: null,
  clearable: false,
  size: 34,
  bare: false,
})

const emit = defineEmits<{ 'update:modelValue': [string | null] }>()

const { t } = useI18n()

const tileSize = computed(() => `${props.size}px`)
</script>

<template>
  <div
    class="color-picker"
    :class="{ 'color-picker--bare': props.bare }"
    :style="{ '--tile-size': tileSize }"
  >
    <div class="color-picker__grid">
      <button
        v-if="props.clearable"
        type="button"
        class="color-picker__tile color-picker__tile--none"
        :class="{ 'color-picker__tile--active': props.modelValue === null }"
        :title="t('common.color_picker.none')"
        :aria-label="t('common.color_picker.none')"
        :aria-pressed="props.modelValue === null"
        @click="emit('update:modelValue', null)"
      >
        <IconCheck v-if="props.modelValue === null" :size="16" :stroke-width="2.4" />
      </button>

      <button
        v-for="name in props.colors"
        :key="name"
        type="button"
        class="color-picker__tile color-tones"
        :style="props.resolve(name)"
        :class="{ 'color-picker__tile--active': name === props.modelValue }"
        :title="name"
        :aria-label="name"
        :aria-pressed="name === props.modelValue"
        @click="emit('update:modelValue', name)"
      >
        <IconCheck v-if="name === props.modelValue" :size="16" :stroke-width="2.4" />
      </button>
    </div>
  </div>
</template>

<style scoped>
/* The same tray as the icon picker's: a sunken panel, tiles read as lying on it.
   No search bar here — a set of fifteen-odd tiles is visible at once, there's nothing to search. */
.color-picker {
  border-radius: 10px;
  background: var(--surface-sunken);
  border: 1px solid var(--border-sunken);
  padding: 10px;
}

/* Without the tray only the grid remains: the surrounding panel is drawn by whoever nested the
   picker, and a second background with a border inside would read as a window within a window. */
.color-picker--bare {
  background: none;
  border: none;
  border-radius: 0;
  padding: 0;
}

.color-picker__grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(var(--tile-size), 1fr));
  gap: 8px;
}

.color-picker__tile {
  background: var(--gc-swatch);
  /* An inset hairline: in the light theme a mid-step tile separates from the tray by only ~2.8:1,
     and without an edge the set reads as a blurry blot. Inset rather than a border so as not to
     change the tile size. */
  box-shadow: inset 0 0 0 1px rgba(0, 0, 0, 0.14);
  display: flex;
  align-items: center;
  justify-content: center;
  aspect-ratio: 1;
  border-radius: 8px;
  border: none;
  cursor: pointer;
  /* The check sits on the fill, and the whole set's fill has one lightness (OKLCH L 0.62), so a
     dark stroke reads on any tile in any theme — the worst pair is 3.93:1 against a threshold of 3. */
  color: rgba(0, 0, 0, 0.72);
  transition: transform 120ms ease, box-shadow 120ms ease;
}

.color-picker__tile:hover {
  transform: scale(1.06);
}

.color-picker__tile:focus-visible {
  outline: 2px solid var(--text);
  outline-offset: 2px;
}

/* "No color" is an empty tile in the card tone: it doesn't take part in the set as a color but shows
   that no color is set, so its check is in the text color rather than dark. */
.color-picker__tile--none {
  background: var(--surface);
  border: 1px dashed var(--border);
  color: var(--text-muted);
  box-shadow: none;
}
</style>
