<script lang="ts">
/** An applied filter: `key` — what to clear, `label` — the value ITSELF, not "Field: value". */
export interface AppliedFilter {
  key: string
  label: string
}
</script>

<script setup lang="ts">
// The strip above a list: the controls row (whatever the page puts into the slot) and, under it,
// the line of what narrows the list right now. Field widths are set here by the `filter-search` /
// `filter-select` classes, so a page does not size its controls itself.
//
// TWO LINES, AND THE SECOND ARRIVES WHOLE. The controls row is always in place; the applied line
// appears only when there is something to show. Kept in one row, an appearing reset would push the
// controls out of place on every pick.
import { useI18n } from 'vue-i18n'
import { IconX } from '@tabler/icons-vue'

const props = withDefaults(defineProps<{
  /** What narrows the list right now — one chip per value. */
  applied?: AppliedFilter[]
  /**
   * Shows the reset even without chips: a changed default (a pressed "show deleted") has nothing
   * to put on a chip, yet there is still something to reset.
   */
  resettable?: boolean
  /** The result of the filter ("42 tasks"), pushed to the right edge of the controls row. */
  total?: string
}>(), {
  applied: () => [],
  resettable: false,
  total: undefined,
})

const emit = defineEmits<{
  remove: [key: string]
  clear: []
}>()

const { t } = useI18n()

function showApplied(): boolean {
  return props.applied.length > 0 || props.resettable
}
</script>

<template>
  <VCard variant="outlined" rounded="lg" class="filter-panel">
    <div class="filter-panel__row">
      <slot />

      <span v-if="total" class="filter-panel__total">{{ total }}</span>
    </div>

    <div v-if="showApplied()" class="filter-panel__applied">
      <!-- The whole chip is the target: it has no other action, and a 12px cross would have to be
           aimed at. The cross stays as the sign that a click removes the filter. -->
      <VChip
        v-for="filter in applied"
        :key="filter.key"
        size="small"
        variant="tonal"
        closable
        role="button"
        :aria-label="t('common.filter.remove', { label: filter.label })"
        class="filter-panel__chip"
        @click="emit('remove', filter.key)"
        @click:close="emit('remove', filter.key)"
      >
        {{ filter.label }}
        <template #close>
          <IconX :size="12" :stroke-width="2.5" />
        </template>
      </VChip>

      <VBtn variant="text" size="small" class="filter-panel__reset" @click="emit('clear')">
        {{ t('common.filter.reset') }}
      </VBtn>
    </div>
  </VCard>
</template>

<style scoped>
.filter-panel {
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding: 10px 12px;
}

/* The controls row wraps: in a narrow window controls move to the next line whole rather than
   squeeze the search. */
.filter-panel__row {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
}

.filter-panel__total {
  flex: none;
  font-size: 12px;
  color: var(--text-muted);
}

/* Search is what the panel is used for every time: wider than the rest, and never below 300px —
   there the placeholder gets cut and the field stops saying what it searches. Controls do not grow,
   otherwise they split the rest of the row and push the toggles to a second line. */
:slotted(.filter-search) {
  flex: 0 1 364px;
  min-width: 300px;
}

/* ⚠️ A LOWER bound, not only an upper one: without it five selects squeeze into one row and the
   label gets an ellipsis instead of the row wrapping. 140px fits the longer Russian wording. */
:slotted(.filter-select) {
  flex: 0 1 164px;
  min-width: 140px;
}

/* Toggles hug the right edge even on a wrapped line: they have a fixed place, rather than one to
   be found anew whenever the fields change. */
:slotted(.filter-toggles) {
  flex: none;
  margin-inline-start: auto;
}

.filter-panel__applied {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 6px;
}

/* A chip is a mark, not a heading: regular weight and a muted color, otherwise it argues with the
   rows of the list below. */
.filter-panel__chip {
  font-size: 12px;
  font-weight: 400;
  color: var(--text-muted);
  max-width: 100%;
  cursor: pointer;
  transition: color 120ms ease;
}

/* A slotted `IconX` instead of the global `$delete` (a circled cross): the circle reads coarse on a
   small chip. Quieter than the text. */
.filter-panel__chip :deep(.v-chip__close) {
  color: var(--text-faint);
  opacity: 1;
  transition: color 120ms ease;
}

/* The whole chip is a button: under the pointer the text, the cross and the underlay darken. The
   Vuetify overlay of chips is cancelled globally (main.scss), so the underlay is raised here. */
.filter-panel__chip:hover,
.filter-panel__chip:focus-visible,
.filter-panel__chip:hover :deep(.v-chip__close),
.filter-panel__chip:focus-visible :deep(.v-chip__close) {
  color: var(--text);
}

.filter-panel__chip:hover :deep(.v-chip__underlay),
.filter-panel__chip:focus-visible :deep(.v-chip__underlay) {
  opacity: 0.2;
}

/* Reset sits AT THE END of the applied line: it belongs to the chips on its left, and pushed to
   the panel edge it would read as a control tied to nothing. */
.filter-panel__reset.v-btn {
  flex: none;
  font-size: 12px;
  color: var(--text-muted);
}

.filter-panel__reset.v-btn:hover {
  color: var(--text);
}

/* On a phone the controls stand one per line anyway, and width caps make the strip ragged: here
   everything takes the full width. */
@media (max-width: 599px) {
  :slotted(.filter-search),
  :slotted(.filter-select) {
    flex: 1 1 100%;
    min-width: 0;
  }

  :slotted(.filter-toggles) {
    margin-inline-start: 0;
  }
}
</style>
