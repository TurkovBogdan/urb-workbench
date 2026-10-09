<script setup lang="ts">
// A text field with a length limit: VTextField or VTextarea, with an "N / limit" counter in the
// corner that looks and behaves like the markdown editor's. A form field and a task body follow one
// convention: a person used to the counter in the detail view finds it in the same place here.
//
// Input stops at the limit: the excess is cut by the native `maxlength`, and typing or pasting more
// is impossible. So the cut never comes as a surprise, the counter changes color in advance — yellow
// from 70% full, red from 90%. A value that arrives longer than the limit (saved before it existed)
// is left untouched: shown in red and reported to the form as `over` so it isn't saved silently.
//
// The counter never moves the layout: its space is always reserved, visible or not. It takes a
// column at the right edge of the field, its width held by an invisible sample of the longest entry
// ("limit / limit"), so typing digits doesn't shift anything and no line ever runs under it.
// - single-line — the counter is centered on the line;
// - multi-line — it sits on the last line. A column rather than a strip under the text: a strip
//   made every field a strip taller than its text, and the empty field's label sat off-center.
//
// Other attributes and slots pass through to the Vuetify field as is.
import { computed, ref, useSlots } from 'vue'
import { VTextarea, VTextField } from 'vuetify/components'

const WARNING_FROM = 70
const DANGER_FROM = 90

const props = withDefaults(defineProps<{
  /** Length limit in characters. */
  maxLength: number
  /**
   * From what fill level to show the counter, in percent. `0` — always visible while the field
   * is focused. Exceeding the limit is shown regardless of the threshold and focus.
   */
  limitThreshold?: number
  /** VTextarea instead of VTextField. */
  multiline?: boolean
}>(), {
  limitThreshold: 0,
  multiline: false,
})

// `null` comes from Vuetify's clear ×; for counting it is the same as an empty string.
const model = defineModel<string | null>({ default: '' })

const slots = useSlots()
const passedSlots = computed(() => Object.keys(slots).filter(name => name !== 'append-inner'))

const focused = ref(false)
const chars = computed(() => model.value?.length ?? 0)
const over = computed(() => chars.value > props.maxLength)
const fill = computed(() => chars.value / props.maxLength * 100)

const level = computed(() => {
  if (fill.value >= DANGER_FROM) return 'is-danger'
  if (fill.value >= WARNING_FROM) return 'is-warning'
  return ''
})

const showLimit = computed(() => {
  if (over.value) return true
  if (!focused.value) return false
  return fill.value >= props.limitThreshold
})

const widest = computed(() => `${props.maxLength} / ${props.maxLength}`)

defineExpose({ over })
</script>

<template>
  <component
    :is="props.multiline ? VTextarea : VTextField"
    v-model="model"
    :maxlength="props.maxLength"
    class="limit-field"
    :class="{ 'limit-field--multiline': props.multiline }"
    @update:focused="focused = $event"
  >
    <template v-for="name in passedSlots" #[name]="scope">
      <slot :name="name" v-bind="scope ?? {}" />
    </template>

    <template #append-inner="scope">
      <slot name="append-inner" v-bind="scope ?? {}" />
      <span class="limit-field__limit" :class="level" aria-hidden="true">
        <span class="limit-field__ghost">{{ widest }}</span>
        <span v-show="showLimit" class="limit-field__count">{{ chars }} / {{ props.maxLength }}</span>
      </span>
    </template>
  </component>
</template>

<style scoped>
/* The counter typography copies `.editor__limit` from MarkdownEditor: the same sign must read
   the same wherever it stands. */
.limit-field__limit {
  font-family: var(--font-mono);
  font-size: 11px;
  line-height: 1;
  color: var(--text-faint);
  font-variant-numeric: tabular-nums;
  pointer-events: none;
  user-select: none;
  white-space: nowrap;
}

/* Yellow — "the limit is near", red — "you'll hit it in a couple of words". Theme colors, not our
   own: in the light theme warning is a dark amber, pure yellow on white wouldn't be readable. */
.limit-field__limit.is-warning {
  color: rgb(var(--v-theme-warning));
  font-weight: 500;
}

.limit-field__limit.is-danger {
  color: rgb(var(--v-theme-error));
  font-weight: 500;
}

/* The sample and the counter share one grid cell, the sample sets the column's width. */
.limit-field__limit {
  display: grid;
  justify-items: end;
}

.limit-field__ghost,
.limit-field__count {
  grid-area: 1 / 1;
}

.limit-field__ghost {
  visibility: hidden;
}

.limit-field:not(.limit-field--multiline) .limit-field__limit {
  align-self: center;
}

/* Multi-line: pinned to the bottom of the column, then lifted by the field's bottom padding plus
   half the gap between the line box (19.5px) and the digits (11px), so it sits centered on the
   last line. The column itself renders with no bottom padding to lean on, hence the full lift
   here. With one row that is the same place the single-line counter takes. */
.limit-field--multiline .limit-field__limit {
  align-self: flex-end;
  margin-bottom: calc(var(--v-field-padding-bottom) + 4px);
}

/* auto-grow computes its floor as `rows × line-height + padding`, but reads the padding from
   Vuetify's own variables (0 + 16 + 16px here) and floors at `--v-input-control-height` (56px) —
   not from the real paddings main.scss sets, so the empty field came out taller than its text.
   The variables are restated with the real values per density (main.scss: 8/8, 6/6, 4/4 and
   floors 36/32/28). The column holding the counter reads the same variables for its padding, so
   its bottom lines up with the textarea's. */
.limit-field--multiline :deep(.v-field) {
  --v-field-padding-top: 8px;
  --v-input-padding-top: 0px;
  --v-field-padding-bottom: 8px;
  --v-input-control-height: 36px;
}

.limit-field--multiline.v-input--density-comfortable :deep(.v-field) {
  --v-field-padding-top: 6px;
  --v-field-padding-bottom: 6px;
  --v-input-control-height: 32px;
}

.limit-field--multiline.v-input--density-compact :deep(.v-field) {
  --v-field-padding-top: 4px;
  --v-field-padding-bottom: 4px;
  --v-input-control-height: 28px;
}

/* auto-grow: Vuetify writes the measured height into `--v-textarea-control-height`, but the
   global density floor (`min-height: 36px` in main.scss, unlayered) beats it and the field never
   grows. Re-honor the measurement on the textarea only — flooring the sizer as well would stop
   its scrollHeight from shrinking, and the field would grow on every keystroke and never come
   back down. */
.limit-field--multiline.v-textarea--auto-grow :deep(.v-field__input:not(.v-textarea__sizer)) {
  min-height: var(--v-textarea-control-height);
}
</style>
