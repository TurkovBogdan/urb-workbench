<script setup lang="ts" generic="T extends string">
// One choice out of a few, where each option needs a sentence to be chosen well — not a button
// row, where only the label fits and the consequence stays unsaid. Each option is a card: a
// title, what choosing it does, and, under the picked one, whatever it still needs (the `details`
// slot — a target to move to, say).
//
// Built on the stock VRadioGroup / VRadio, not drawn by hand: the radio glyph, the keyboard (one
// tab stop, arrows move the choice and skip disabled options), focus and disabled state are the
// same as every other radio in the app. This component adds only the card around each radio —
// in the look of the design system's radio cards (`/design-system/toggle`, "icon cards") — the
// description, and the details under the picked card.
import { Comment, Fragment, useSlots } from 'vue'
import type { VNode } from 'vue'

export interface ChoiceCard<V extends string = string> {
  value: V
  title: string
  description: string
  disabled?: boolean
}

const props = defineProps<{
  items: ChoiceCard<T>[]
  /** Accessible name of the group — what is being chosen. */
  label: string
}>()

const model = defineModel<T | null>({ default: null })

// The whole card picks, not only the radio and its label: the padding around them is part of the
// target the eye aims at.
function pick(item: ChoiceCard<T>) {
  if (!item.disabled) model.value = item.value
}

const slots = useSlots()

// A `v-if` inside the slot leaves a comment node, not nothing: one `#details` template usually
// serves every card and fills only some, and the empty ones still opened their box — its padding
// showed up as a gap under the picked card. So the box opens only for what renders something.
function rendersSomething(nodes: VNode[] | undefined): boolean {
  return (nodes ?? []).some((node) =>
    node.type === Fragment ? rendersSomething(node.children as VNode[]) : node.type !== Comment,
  )
}

function hasDetails(item: ChoiceCard<T>): boolean {
  return rendersSomething(slots.details?.({ item }))
}
</script>

<template>
  <VRadioGroup v-model="model" :aria-label="props.label" hide-details class="choice-cards">
    <div
      v-for="item in props.items"
      :key="item.value"
      class="choice-card"
      :class="{ 'is-disabled': item.disabled }"
      @click="pick(item)"
    >
      <VRadio :value="item.value" :disabled="item.disabled" class="choice-card__radio">
        <template #label>
          <span class="choice-card__text">
            <span class="choice-card__title">{{ item.title }}</span>
            <span class="choice-card__description">{{ item.description }}</span>
          </span>
        </template>
      </VRadio>

      <!-- Clicks inside the details (a select, say) must not re-pick. They unfold by height rather
           than popping in: the cards below move, and a jump would read as the dialog rearranging
           itself. -->
      <VExpandTransition>
        <div v-if="model === item.value && hasDetails(item)" class="choice-card__details" @click.stop @keydown.stop>
          <div class="choice-card__details-inner">
            <slot name="details" :item="item" />
          </div>
        </div>
      </VExpandTransition>
    </div>
  </VRadioGroup>
</template>

<style scoped>
.choice-cards :deep(.v-selection-control-group) { gap: 8px; }

/* The card follows the design system's radio cards: neutral border at rest, accent border with
   the soft tint when picked, the app's 0.15s ease on every change. Hover is the app's clickable
   card hover — an accent border — and keyboard focus its ring. */
.choice-card {
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  padding: 6px 12px 8px 4px;
  cursor: pointer;
  transition:
    border-color 0.15s ease,
    background-color 0.15s ease,
    box-shadow 0.15s ease;
}

.choice-card:hover:not(.is-disabled) { border-color: var(--accent); }

.choice-card:has(input:checked) {
  border-color: var(--accent);
  background: var(--accent-soft);
}

.choice-card:has(.v-selection-control--focus-visible) { box-shadow: 0 0 0 2px var(--accent-soft); }

.choice-card.is-disabled { cursor: default; }

/* A two-line label: the radio stands by the title line, not in the middle of the text, and the
   label wraps instead of being cut. */
.choice-card__radio { align-items: flex-start; }

.choice-card__radio :deep(.v-label) {
  white-space: normal;
  padding-top: 9px;
  cursor: inherit;
}

.choice-card__text {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

/* The project's type scale for a radio and the text under it: the label is the radio label
   (13px, as `.v-label` and the design system's radio cards set it, at medium weight), the
   description is a hint (12px muted, as field hints and dialog notes). */
.choice-card__title {
  font-size: 13px;
  font-weight: 500;
  line-height: 1.5;
  color: var(--text);
}

.choice-card__description {
  font-size: 12px;
  line-height: 1.45;
  color: var(--text-muted);
}

/* Aligned with the label text, past the radio's column. */
.choice-card__details {
  margin-left: 36px;
  cursor: default;
}

/* The gap above the details is padding on an inner box, not margin on the unfolding one: the
   expand transition animates the outer box's height, and a margin outside it would jump in whole
   at the start instead of opening with it. */
.choice-card__details-inner { padding-top: 6px; }

@media (prefers-reduced-motion: reduce) {
  .choice-card :deep(.expand-transition-enter-active),
  .choice-card :deep(.expand-transition-leave-active) { transition: none !important; }
}
</style>
