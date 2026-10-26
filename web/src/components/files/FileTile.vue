<script setup lang="ts">
// The square a file's card leads with: the picture itself when the file is one (`src`) and the
// browser can draw it, otherwise the glyph of the file's kind on that kind's colour — a spreadsheet
// green, a PDF red (`shared/utils/file-icon.ts`). The colour is a palette name resolved for the
// theme by `.color-tones`: the glyph takes the readable tone, the plate its soft tint.
//
// A picture the browser fails on goes back to its kind's square for as long as its address stays.
// The name stands right beside the tile, so the tile says nothing a reader needs: no alt.
import { computed, ref, watch } from 'vue'

import { colorVarsByName } from '@/shared/colors'
import { fileColor, fileIcon } from '@/shared/utils/file-icon'

const props = defineProps<{
  /** The file's name with its extension — the kind when the type says nothing. */
  name: string
  mime: string
  /** The picture's address; unset — the file is not a picture, the glyph stands. */
  src?: string
}>()

const failed = ref(false)

watch(() => props.src, () => { failed.value = false })

const glyph = computed(() => fileIcon(props.name, props.mime))
const tone = computed(() => colorVarsByName(fileColor(props.name, props.mime)))
</script>

<template>
  <!-- Dragged by the card's handle, not by the picture. -->
  <img
    v-if="src && !failed"
    :src="src"
    alt=""
    loading="lazy"
    decoding="async"
    draggable="false"
    class="file-tile file-tile--picture"
    @error="failed = true"
  >
  <span v-else class="file-tile color-tones" :style="tone" aria-hidden="true">
    <component :is="glyph" :size="22" :stroke-width="1.6" />
  </span>
</template>

<style scoped>
.file-tile {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  flex: none;
  width: 40px;
  height: 40px;
  border-radius: var(--radius-sm);
  background: var(--gc-fill);
  color: var(--gc-ink);
}

/* Cut to the square from the middle, not squeezed. The well colour holds the place while the file
   loads, and the hairline keeps a white picture from melting into the white card. */
.file-tile--picture {
  object-fit: cover;
  border: 1px solid var(--border-soft);
  background: var(--surface-sunken);
}
</style>
