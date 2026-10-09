<script setup lang="ts">
// Icon and color choice in one panel: the glyph and the tone aren't two independent fields but one
// badge, judged as a whole. So at the top is a preview — the very badge that will end up on the
// card — with the palette beside it, and below the rule the icon set with search.
//
// Built from two primitives in `bare` mode: there is one tray here, shared by both choices; each
// with its own tray would read as two windows placed side by side.
//
// The color reaches the icons by itself: the `--gc-ink` / `--gc-fill` roles are declared on the
// root (`.color-tones`) and inherited, so the selected icon tile takes the selected color — the link
// between the two halves of the panel shows without a single prop between them.
import { computed } from 'vue'

import ColorPicker from '@/components/ColorPicker.vue'
import IconPicker from '@/components/IconPicker.vue'
import type { ColorToneVars } from '@/shared/colorTones'
import type { TablerIcon } from '@/shared/nav'

const icon = defineModel<string | null>('icon', { default: null })
const color = defineModel<string | null>('color', { default: null })

const props = withDefaults(defineProps<{
  /** The full set of icon codes in display order. */
  icons: string[]
  /** The full set of color names in display order. */
  colors: string[]
  /** Code → icon component; `null` — no icon selected (the resolver returns a fallback). */
  resolveIcon: (name: string | null) => TablerIcon
  /** Name → color steps as variables; `null` — no color selected (the resolver returns a fallback tone). */
  resolveColor: (name: string | null) => ColorToneVars
  /** Height of the icon area; beyond it the area scrolls. */
  height?: number | string
  /** Allow "no color" — a reset tile in the palette. */
  clearable?: boolean
}>(), {
  height: 200,
  clearable: false,
})

const tones = computed(() => props.resolveColor(color.value))
</script>

<template>
  <div class="icon-color-picker color-tones" :style="tones">
    <div class="icon-color-picker__head">
      <span class="icon-color-picker__preview">
        <component :is="props.resolveIcon(icon)" :size="18" :stroke-width="1.6" />
      </span>
      <ColorPicker
        v-model="color"
        :colors="props.colors"
        :resolve="props.resolveColor"
        :clearable="props.clearable"
        :size="26"
        bare
      />
    </div>

    <div class="icon-color-picker__rule" />

    <IconPicker
      v-model="icon"
      :icons="props.icons"
      :resolve="props.resolveIcon"
      :height="props.height"
      bare
    />
  </div>
</template>

<style scoped>
/* The same tray as the single pickers' — a sunken panel, with the content lying on it. */
.icon-color-picker {
  display: flex;
  flex-direction: column;
  border-radius: 10px;
  background: var(--surface-sunken);
  border: 1px solid var(--border-sunken);
  overflow: hidden;
}

/* Preview and palette in one band: a color is chosen by looking at the badge, not at the tile. */
.icon-color-picker__head {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 10px;
}

/* The same badge as on the card: the result of both choices, not a color sample. */
.icon-color-picker__preview {
  flex: none;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 30px;
  height: 30px;
  border-radius: 8px;
  color: var(--gc-ink);
  background: var(--gc-fill);
}

/* The palette takes the rest of the band: the tiles stretch, and ten fit in one row. */
.icon-color-picker__head :deep(.color-picker) {
  flex: 1;
  min-width: 0;
}

/* A rule across the full tray width — the same role as the rule under a window header: it separates
   the color band from the icon set. The paddings live in the bands, not on the panel. */
.icon-color-picker__rule {
  height: 1px;
  background: var(--border);
}
</style>
