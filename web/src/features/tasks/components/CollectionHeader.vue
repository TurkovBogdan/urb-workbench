<script setup lang="ts">
// The header of a collection section on the task page — notes, journal, subtasks: a title with a
// "?" on the left, an add button on the right. No count: the items are right below, and how many
// there are is not what the header is read for.
//
// On the canvas the title is inset to the line of the titles inside the cards above it (their
// border and 16px padding), so the page column reads as one edge of headings, carded or not. Inside
// a card (`inCard`) the card's own padding does that, and the header drops its outer margins too.
//
// Add disappears rather than greys out where nothing may be added (a deleted task): a disabled
// button would only say "not here", and it says so every time the page is read. The `actions` slot
// takes what else acts on the whole set — a filter — and stands left of add.
import { IconPlus } from '@tabler/icons-vue'

import SectionHeader from '@/components/SectionHeader.vue'

defineProps<{
  title: string
  hint?: string
  /** The add button's label; omitted — no button. */
  addLabel?: string
  /** Adding is in flight. */
  adding?: boolean
  /** The header stands inside the section's card rather than above it on the canvas. */
  inCard?: boolean
  /** Nothing follows the header: it keeps the same space below as above. */
  empty?: boolean
}>()

const emit = defineEmits<{ add: [] }>()
</script>

<template>
  <SectionHeader
    :title="title"
    :hint="hint"
    class="collection-header"
    :class="{ 'collection-header--in-card': inCard, 'collection-header--empty': empty }"
  >
    <template v-if="addLabel || $slots.actions" #right>
      <slot name="actions" />
      <VBtn v-if="addLabel" variant="text" size="small" :loading="adding" @click="emit('add')">
        <template #prepend><IconPlus :size="16" /></template>
        {{ addLabel }}
      </VBtn>
    </template>
  </SectionHeader>
</template>

<style scoped>
.collection-header { padding-inline-start: 17px; }

/* SectionHeader leaves 10px under itself for its content and 4px above. With no content the 10px
   would hang under the header alone and the section would sit closer to what is above it than to
   what is below — so the bottom takes the top's 4px. Tripled class: see the next rule. */
.collection-header.collection-header--empty.collection-header--empty {
  margin-bottom: 4px;
}

/* Doubled class: it has to outweigh SectionHeader's own `.section-header:not(--l1)` margin. */
.collection-header.collection-header--in-card.collection-header--in-card {
  padding-inline-start: 0;
  margin: 0;
}
</style>
