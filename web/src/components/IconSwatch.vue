<script setup lang="ts">
// An object's mark as one badge: its icon in its color. Workspaces, zones and research shelves all
// have an "icon + color" pair — and the object is recognized by it wherever it is mentioned: in a
// list card, in a picker row, in the header of another list. So there is one badge for all, and its
// size is set by the place it is put in.
//
// There are deliberately no domain types here (the promotion rule, docs/conventions/frontend.md):
// the inputs are two names from shared registries, and the component doesn't know whose mark it draws.
//
// The WIDTH is set and the icon size derives from it: the badge is square, and a second value would
// just be a way to make it disagree with itself.
//
// The rounding, however, does NOT depend on width: the system has two radius steps (`--radius` 10px
// for cards, `--radius-sm` 6px for buttons and fields), and the badge belongs to the second step at
// any size. If the radius were a share of the width, each badge size would get its own rounding — a
// third scale beside the two shared ones, and next to a 6px icon button the badge would look
// over-rounded.
import { computed } from 'vue'

import { colorVarsByName } from '@/shared/colors'
import { iconByName } from '@/shared/icons'

const ICON_SHARE_OF_WIDTH = 0.7

const props = withDefaults(defineProps<{
  /** A name from the `shared/icons.ts` registry; empty — the fallback icon. */
  icon: string
  /** A name from the `shared/colors.ts` registry; empty — the app accent. */
  color: string
  /** Badge side in pixels. */
  width?: number
}>(), {
  width: 22,
})

const iconSize = computed(() => Math.round(props.width * ICON_SHARE_OF_WIDTH))

const boxStyle = computed(() => ({
  '--icon-swatch-width': `${props.width}px`,
  ...colorVarsByName(props.color),
}))
</script>

<template>
  <span class="icon-swatch color-tones" :style="boxStyle">
    <component :is="iconByName(props.icon)" :size="iconSize" :stroke-width="1.7" />
  </span>
</template>

<style scoped>
.icon-swatch {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: var(--icon-swatch-width);
  height: var(--icon-swatch-width);
  border-radius: var(--radius-sm);
  flex: none;
  /* The object's color, or without one the app accent: the same fallback path as the icon's. */
  color: var(--gc-ink, var(--accent));
  background: var(--gc-fill, var(--accent-soft));
}
</style>
