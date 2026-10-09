<script setup lang="ts">
// IN-PLACE value editing: text at rest, and on the pencil — a field in the same spot with the same metrics.
//
// Entering edit mode moves the layout on neither axis. Vertically that is the job of a single
// `--ile-height` token: the height is the same at rest, in edit mode and without edit rights, and
// the text at rest is single-line with an ellipsis (wrapping would make height depend on value length).
// Horizontally — both the text and the field take the width of THEIR CONTENT, not all the free
// space: the field opens exactly as wide as the text was, so the button stays where the pencil
// was. Cancel appears to its right and grows outward, shifting nothing.
import { computed, nextTick, ref, useSlots, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { IconCheck, IconLoader2, IconPencil, IconX } from '@tabler/icons-vue'

const props = withDefaults(defineProps<{
  /** The stored value. An empty string = no value. */
  value: string
  /** The value's name: the field label for screen readers. */
  label: string
  /** The pencil's label. Defaults to the value's name, so adjacent rows don't share a label. */
  editLabel?: string
  /** What to show at rest if not `value` itself (a country: code in the database, name on screen). */
  display?: string
  /** Text shown in place of an empty value. */
  empty?: string
  placeholder?: string
  editable?: boolean
  /** A request for THIS value is in flight: the pencil spins, editing is locked. */
  saving?: boolean
  maxlength?: number
  /** `field` — a property row, `title` — a page heading. They differ only in metrics. */
  variant?: 'field' | 'title'
  /** Heading level in the accessibility tree; without it the text stays a plain `span`. */
  heading?: 1 | 2 | 3 | 4 | 5 | 6
  /** An empty value is allowed and means "erase". By default saving an empty value is forbidden. */
  allowEmpty?: boolean
}>(), {
  editLabel: undefined,
  display: undefined,
  empty: '',
  placeholder: undefined,
  editable: false,
  saving: false,
  maxlength: undefined,
  variant: 'field',
  heading: undefined,
  allowEmpty: false,
})

const emit = defineEmits<{ save: [string] }>()

/** Exposed so the owner can close editing itself: when a new value arrives or the right is lost. */
const editing = defineModel<boolean>('editing', { default: false })

const { t } = useI18n()
const slots = useSlots()

const draft = ref('')
const text = ref<HTMLElement | null>(null)
const action = ref<HTMLButtonElement | null>(null)
const field = ref<HTMLInputElement | null>(null)

const shown = computed(() => props.display ?? props.value)
const blank = computed(() => shown.value === '')
const draftBlank = computed(() => draft.value.trim() === '')

/** What the field width is measured by: the typed text, or the placeholder when empty so it shows in full. */
const sizerText = computed(() => draft.value || props.placeholder || '')

/** With its own control (a country list) the owner drives editing: there is no "input" to confirm. */
const custom = computed(() => slots.control !== undefined)

async function start(): Promise<void> {
  if (!props.editable) return

  draft.value = props.value
  editing.value = true

  await nextTick()

  const input = field.value
  if (input === null) return

  input.focus()
  // Caret at the START of the line: `focus()` puts it at the end, but values are edited from the start more often.
  input.setSelectionRange(0, 0)
  // The caret doesn't drag the scroll along when the value is wider than the field: `focus()` has
  // already scrolled to the end, and the person would see the name's tail with the caret at the start. Reset by hand.
  input.scrollLeft = 0
}

/** Close editing and return focus to the pencil — otherwise it falls to `body`. */
function close(): void {
  editing.value = false
  draft.value = ''

  void nextTick(() => action.value?.focus())
}

function cancel(): void {
  if (!editing.value) return

  close()
}

function submit(): void {
  if (props.saving || (draftBlank.value && !props.allowEmpty)) return

  const next = draft.value.trim()

  // Nothing changed — close silently, no request is needed for the same value.
  if (next === props.value) {
    close()
  } else {
    emit('save', next)
  }
}

// The right may vanish mid-edit (the card was re-read) — close editing, otherwise the person is
// left in a field without buttons.
watch(() => props.editable, (allowed) => {
  if (!allowed) cancel()
})

defineExpose({ close })
</script>

<template>
  <span class="ile" :class="`ile--${variant}`">
    <!-- The owner's own control (a dropdown): keeps the same row height as the field. -->
    <span v-if="editing && custom" class="ile__control">
      <slot name="control" :cancel="cancel" />
    </span>

    <!-- `data-value` IS the field width: the wrapper draws the same string as an invisible copy
         (see styles), the field stretches to it and grows as you type. -->
    <span
      v-else-if="editing"
      class="ile__text ile__grow"
      :data-value="sizerText"
    >
      <!-- `size="1"` is not the on-screen field size but a waiver of its own width: by default an input
           asks for ~20 characters, and on a shorter name it, not the text, would dictate the width. -->
      <input
        ref="field"
        v-model="draft"
        class="ile__input"
        type="text"
        size="1"
        :maxlength="maxlength"
        :placeholder="placeholder"
        :disabled="saving"
        :aria-label="label"
        @keydown.enter.prevent="submit"
        @keydown.esc.prevent="cancel"
      />
    </span>

    <span
      v-else
      ref="text"
      class="ile__text ile__value"
      :class="{ 'ile__value--blank': blank }"
      :role="heading ? 'heading' : undefined"
      :aria-level="heading"
      :title="shown || undefined"
      @dblclick="start()"
    >{{ blank ? empty : shown }}</span>

    <template v-if="editable">
      <!-- A custom control needs no confirm: it saves on selection and has no input. -->
      <button
        v-if="!(editing && custom)"
        ref="action"
        type="button"
        class="ile__btn"
        :class="{ 'ile__btn--framed': editing, 'ile__btn--busy': saving }"
        :disabled="saving || (editing && draftBlank && !allowEmpty)"
        :title="editing ? t('common.action.save') : (editLabel ?? label)"
        :aria-label="editing ? t('common.action.save') : (editLabel ?? label)"
        @click="editing ? submit() : start()"
      >
        <IconLoader2 v-if="saving" :size="16" class="icon-spin" />
        <IconCheck v-else-if="editing" :size="16" />
        <IconPencil v-else :size="16" />
      </button>

      <!-- Cancel doesn't just fade in, it pushes room open for itself: with opacity alone the
           neighbouring check would jump by a button's width on the very first frame. -->
      <Transition name="ile-btn">
        <button
          v-if="editing"
          type="button"
          class="ile__btn ile__btn--framed"
          :disabled="saving"
          :title="t('common.action.cancel')"
          :aria-label="t('common.action.cancel')"
          @click="cancel"
        >
          <IconX :size="16" />
        </button>
      </Transition>
    </template>
  </span>
</template>

<style scoped>
/* The row height is the only size fixed rigidly here: the promise "editing doesn't move the
   layout" rests on it. The button is exactly this tall, and so are the text and the field. */
.ile {
  display: flex;
  align-items: center;
  gap: 6px;
  min-width: 0;
  height: var(--ile-height);

  /* Room for the caret after the last character. BOTH states carry it: the field so a caret at the
     end of the line doesn't stick to its edge, the text at rest so the field opens exactly its
     width rather than these pixels wider. */
  --ile-caret: 2px;
}

.ile--field {
  --ile-height: 28px;
  --ile-size: 15px;
  --ile-weight: 600;
}

/* Page heading: size and weight shared with `SectionHeader --l1` (18px / 600), the height is its
   line box (18 × 1.3, rounded up). The metrics are duplicated rather than taken from a token:
   `SectionHeader` sets them by a class rule, there is nothing to export. */
.ile--title {
  --ile-height: 24px;
  --ile-size: 18px;
  --ile-weight: 600;
}

/* BOTH states hold the metrics, text and field alike: if they diverged, pressing would cause a jump. */
.ile__text {
  min-width: 0;
  font-size: var(--ile-size);
  font-weight: var(--ile-weight);
  line-height: 1.3;
  color: var(--text);
}
.ile--title .ile__text { letter-spacing: -0.02em; }

/* Single line with an ellipsis: wrapping to a second line would make the height depend on the
   value length, and in edit mode it would return to one line anyway — that is, a jump.

   The width follows the letters (`flex: 0 1 auto`, like the field wrapper below), not all the free
   space: the pencil sits right against the text and the field opens exactly in its place. The value
   must not take the free row also because then there would be nowhere to "grow while typing". */
.ile__value {
  flex: 0 1 auto;
  padding-right: var(--ile-caret);
  overflow: hidden;
  white-space: nowrap;
  text-overflow: ellipsis;
}
.ile__value--blank { color: var(--text-muted); font-weight: 400; }

/* A field as wide as its own text, without a single JS measurement: the wrapper is a one-cell grid
   holding both the field and an invisible copy of the typed text (`::after` with
   `attr(data-value)`). The copy stretches the cell, the field follows, so the width tracks input.

   `min-width: 0` on the cell is required: without it the cell won't shrink below the string length,
   and on a long value the field would overflow on top of the buttons instead of stopping at the edge
   and scrolling inside itself. The floor for a fully erased value is `size="1"` on the field itself. */
.ile__grow {
  display: inline-grid;
  flex: 0 1 auto;
  min-width: 0;
  max-width: 100%;
  padding-right: var(--ile-caret);
}
.ile__grow::after,
.ile__input {
  grid-area: 1 / 1;
  min-width: 0;
  width: auto;
}

/* `pre` so the copy measures spaces the way the field shows them, otherwise text typed with a double
   space would measure shorter than it looks. */
.ile__grow::after {
  content: attr(data-value);
  visibility: hidden;
  white-space: pre;
}

/* The field is colorless: no background, no border, no padding of its own — only the text stays on
   screen, and the buttons on the right signal edit mode. Metrics come wholly from the wrapper
   (`font: inherit`), otherwise the copy and the field would measure different fonts and the widths would diverge. */
.ile__input {
  padding: 0;
  border: 0;
  background: transparent;
  font: inherit;
  letter-spacing: inherit;
  appearance: none;
}
.ile__input:focus { outline: none; }
.ile__input:disabled { color: var(--text-muted); }

/* A foreign control fits the same height: otherwise Vuetify brings its own (40px for `compact`). */
.ile__control { flex: 1 1 auto; min-width: 0; }
.ile__control :deep(.v-field) { min-height: var(--ile-height); }
.ile__control :deep(.v-field__input) { min-height: var(--ile-height); padding-top: 0; padding-bottom: 0; }

/* Own buttons, not `VBtn`: that one has its own height and density, which make the row taller in
   edit mode — exactly what this component must not allow.

   They sit right against the value, not at the row's right edge: at the edge they would drift apart
   from the text by the whole empty width, and the eye would have to travel back from pencil to name. */
.ile__btn {
  flex: 0 0 auto;
  box-sizing: border-box;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: var(--ile-height);
  height: var(--ile-height);
  padding: 0;
  border: 1px solid transparent;
  border-radius: var(--radius-sm);
  background: transparent;
  color: var(--text-faint);
  cursor: pointer;
  transition: color 0.15s ease, background 0.15s ease, border-color 0.15s ease;
}
.ile__btn:hover:not(:disabled) { background: var(--surface-hi); color: var(--text); }
.ile__btn:focus-visible { outline: 2px solid var(--accent); outline-offset: 2px; }
.ile__btn:disabled { cursor: default; opacity: 0.5; }

/* In edit mode the buttons stop being ghosts: a fill one step darker than the canvas (`--surface-hi`
   vs `--bg`) plus a hairline border. The border is declared transparent ABOVE rather than added here:
   otherwise the button would grow by 2px on entering edit mode. */
.ile__btn--framed {
  background: var(--surface-hi);
  border-color: var(--border-soft);
  color: var(--text-muted);
}
.ile__btn--framed:hover:not(:disabled) { background: var(--surface-sunken); color: var(--text); }

/* A busy button is not "dimmed": the request is running, and the spinner shows at full strength. */
.ile__btn--busy { opacity: 1; color: var(--text-muted); }

.ile-btn-enter-active,
.ile-btn-leave-active {
  overflow: hidden;
  transition: opacity 160ms ease, width 220ms ease, margin-left 220ms ease;
}
.ile-btn-enter-from,
.ile-btn-leave-to {
  width: 0;
  margin-left: -6px;
  opacity: 0;
}
</style>
