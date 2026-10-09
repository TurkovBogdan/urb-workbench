<script setup lang="ts">
/**
 * A VSelect with "previous" / "next" buttons on either side.
 *
 * For where the options stand in a meaningful order (size, weight, height, page step) and
 * neighbours are tried one after another while comparing the result: opening the list for a
 * one-item step is three moves instead of one. The list still stays: jumping to a distant option
 * with the buttons would take long.
 *
 * The ends don't wrap: after the last item comes not the first but a disabled button — otherwise a
 * person clicking the step overshoots the set boundary without noticing. When nothing is
 * selected, stepping forward takes the first item, back — the last.
 *
 * Everything else is a pass-through VSelect: `$attrs` and slots go into it, so replacing
 * VSelect → VSelectStepper requires nothing more.
 */
import { computed, useAttrs, useSlots } from 'vue'
import { useI18n } from 'vue-i18n'
import { IconChevronLeft, IconChevronRight } from '@tabler/icons-vue'

const model = defineModel<unknown>()

const props = withDefaults(defineProps<{
  items: unknown[]
  /** The object field that goes into the model (mirrors VSelect's `item-value`). */
  itemValue?: string
  /** Density is set here rather than as an attribute: the field and both buttons all hold it. */
  density?: 'default' | 'comfortable' | 'compact'
  prevLabel?: string
  nextLabel?: string
}>(), {
  itemValue: 'value',
  density: 'default',
})

const { t } = useI18n()

defineOptions({ inheritAttrs: false })

const NOTHING_SELECTED = -1

function valueOf(item: unknown): unknown {
  if (item !== null && typeof item === 'object') {
    return (item as Record<string, unknown>)[props.itemValue]
  }
  return item
}

const index = computed(() => props.items.findIndex((item) => valueOf(item) === model.value))

const lastIndex = computed(() => props.items.length - 1)

const atFirst = computed(() => index.value === 0)
const atLast = computed(() => index.value === lastIndex.value)

function step(delta: number): void {
  if (lastIndex.value < 0) return
  const target =
    index.value === NOTHING_SELECTED
      ? (delta > 0 ? 0 : lastIndex.value)
      : Math.min(Math.max(index.value + delta, 0), lastIndex.value)
  model.value = valueOf(props.items[target])
}

const iconSize = computed(() => (props.density === 'default' ? 18 : 16))

const slots = useSlots()
const forwardedSlots = computed(() => Object.keys(slots))

// The call site's styling belongs to the trio as a whole (width, margins), the remaining
// attributes to the field: without this split a width class would land on the inner field and the
// buttons would end up outside its bounds.
const attrs = useAttrs()

// The field is disabled via an attribute, which goes into VSelect with the rest — the buttons get
// nothing, and stepping would change the model of a disabled field. An empty string is the
// valueless form of the attribute (`disabled`), and it means "yes".
const disabled = computed(() => attrs.disabled === '' || attrs.disabled === true)

const groupClass = computed(() => attrs.class)
const groupStyle = computed(() => attrs.style)
const selectAttrs = computed(() => {
  const { class: _class, style: _style, ...rest } = attrs
  return rest
})
</script>

<template>
  <div class="field-group" :class="groupClass" :style="groupStyle">
    <VBtn
      variant="outlined"
      :density="density"
      icon
      class="field-group__btn field-group__btn--before"
      :aria-label="prevLabel ?? t('common.action.previous')"
      :disabled="disabled || atFirst"
      @click="step(-1)"
    >
      <IconChevronLeft :size="iconSize" />
    </VBtn>

    <VSelect
      v-bind="selectAttrs"
      v-model="model"
      :items="items"
      :item-value="itemValue"
      :density="density"
    >
      <template v-for="name in forwardedSlots" #[name]="slotProps" :key="name">
        <slot :name="name" v-bind="slotProps ?? {}" />
      </template>
    </VSelect>

    <VBtn
      variant="outlined"
      :density="density"
      icon
      class="field-group__btn"
      :aria-label="nextLabel ?? t('common.action.next')"
      :disabled="disabled || atLast"
      @click="step(1)"
    >
      <IconChevronRight :size="iconSize" />
    </VBtn>
  </div>
</template>

<style scoped>
/* The call site sets the width of the trio as a whole, not of the inner field: the side buttons take
   their own box, the field takes the rest. `min-width: 0` is required, otherwise the field hits its
   own minimum width and pushes a button past the edge. */
.v-select {
  flex: 1 1 auto;
  min-width: 0;
}
</style>
