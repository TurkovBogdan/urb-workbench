<script setup lang="ts">
// In-place PARAGRAPH editing — the multi-line sibling of `InlineEdit`. Exactly one difference:
// there the value is one line edited in an input, here the text spans several lines and the field
// is not visible at all. At rest it is a paragraph; in edit mode the same paragraph, just editable:
// same typeface, size, line height and width, no border, no fill, no size of its own.
//
// The promise is the same as `InlineEdit`'s: entering edit mode doesn't move the layout. A paragraph
// has no fixed height for that, so the field measures itself (`scrollHeight`) on open and on every
// input. An invisible CSS copy of the text would look cheaper, but it wraps lines differently from
// the field: measured on a live description it gave 238px versus 208px for the same paragraph.
//
// The component doesn't save: it emits `save` upward and waits for the owner to close editing.
import { computed, nextTick, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { IconCheck, IconLoader2, IconPencil, IconX } from '@tabler/icons-vue'

const props = withDefaults(defineProps<{
  /** The stored value. An empty string = no value. */
  value: string
  /** The value's name: the field label for screen readers. */
  label: string
  /** Text shown in place of an empty value. */
  empty?: string
  /** A request for THIS value is in flight: editing is locked, the buttons don't respond. */
  saving?: boolean
  maxlength?: number
  /** An empty value is allowed and means "erase". */
  allowEmpty?: boolean
}>(), {
  empty: '',
  saving: false,
  maxlength: undefined,
  allowEmpty: false,
})

const emit = defineEmits<{ save: [string] }>()

/** Exposed — the owner opens editing (the "Edit" link next to it) and closes it on the response. */
const editing = defineModel<boolean>('editing', { default: false })

const { t } = useI18n()

const draft = ref('')
const field = ref<HTMLTextAreaElement | null>(null)

const blank = computed(() => props.value === '')
const draftBlank = computed(() => draft.value.trim() === '')

/** Field height = its text height: `auto` resets the previous one, otherwise `scrollHeight` never shrinks. */
function fitHeight(): void {
  const input = field.value
  if (input === null) return

  input.style.height = 'auto'
  input.style.height = `${input.scrollHeight}px`
}

// The draft starts from the current value and the caret goes to the start: `focus()` moves it to
// the end, but text is edited from the start more often.
watch(editing, async (open) => {
  if (!open) {
    draft.value = ''
    return
  }

  draft.value = props.value
  await nextTick()
  fitHeight()
  field.value?.focus()
  field.value?.setSelectionRange(0, 0)
})

function cancel(): void {
  editing.value = false
}

function submit(): void {
  if (props.saving || (draftBlank.value && !props.allowEmpty)) return

  const next = draft.value.trim()

  // Nothing changed — close silently, no request is needed for the same text.
  if (next === props.value) cancel()
  else emit('save', next)
}
</script>

<template>
  <div class="ieb">
    <textarea
      v-if="editing"
      ref="field"
      v-model="draft"
      class="ieb__field"
      rows="1"
      :maxlength="maxlength"
      :disabled="saving"
      :aria-label="label"
      @input="fitHeight"
      @keydown.esc.prevent="cancel"
      @keydown.enter.ctrl.prevent="submit"
      @keydown.enter.meta.prevent="submit"
    />

    <p
      v-else
      class="ieb__value"
      :class="{ 'ieb__value--blank': blank }"
      @dblclick="editing = true"
    >{{ blank ? empty : value }}</p>

    <!-- The same row in both states: actions on the text on the left, what the owner reports about
         it (the update date) on the right. It never appears or disappears, only its left half
         changes, so entering edit mode doesn't move the card. The actions use `link-action`
         (a shared class in main.scss): they continue the text rather than form a control panel for it. -->
    <div class="ieb__row">
      <div class="ieb__actions">
        <template v-if="editing">
          <button
            type="button"
            class="link-action"
            :disabled="saving || (draftBlank && !allowEmpty)"
            @click="submit"
          >
            <IconLoader2 v-if="saving" :size="14" :stroke-width="1.8" class="icon-spin" />
            <IconCheck v-else :size="14" :stroke-width="1.8" />
            {{ t('common.action.save') }}
          </button>

          <button type="button" class="link-action" :disabled="saving" @click="cancel">
            <IconX :size="14" :stroke-width="1.8" />
            {{ t('common.action.cancel') }}
          </button>
        </template>

        <button v-else type="button" class="link-action" @click="editing = true">
          <IconPencil :size="14" :stroke-width="1.8" />
          {{ t('common.action.edit') }}
        </button>
      </div>

      <slot name="aside" />
    </div>
  </div>
</template>

<style scoped>
/* The text metrics are set by the PLACE the component is put in (a class on the root): typeface,
   size, line height and measure come from outside and everything inside inherits them — so rest
   and edit look the same by definition, not by coincidence of settings. */
.ieb {
  display: block;
}

/* The metrics are taken from the root EXPLICITLY: the bare `p` rule in `main.scss` sits outside
   the layers and inheritance can't beat it — the paragraph silently drifted to its own line height
   (20.8 versus 23.8), i.e. the text at rest sat differently than in edit mode. */
.ieb__value {
  margin: 0;
  font: inherit;
  line-height: inherit;
  letter-spacing: inherit;
  color: inherit;
  white-space: pre-wrap;
  cursor: text;
}

.ieb__value--blank {
  color: var(--text-faint);
}

/* The field is invisible: no border, no fill, no metrics of its own — the screen shows only text
   with a caret in it. The script sets the height, so the field needs no scrolling of its own. */
.ieb__field {
  display: block;
  width: 100%;
  margin: 0;
  padding: 0;
  border: 0;
  background: transparent;
  color: inherit;
  font: inherit;
  line-height: inherit;
  letter-spacing: inherit;
  /* The browser resets text rendering to `auto` on form elements, while the surrounding text is set
     with `optimizeLegibility` — ligatures and kerning. Without this line edit mode would differ from
     rest in letterforms: the only discrepancy left after comparing every computed property. */
  text-rendering: inherit;
  resize: none;
  overflow: hidden;
  outline: none;
}

/* Actions on the left, the owner's details on the right — at opposite edges, not in one run: one is
   an action on the text, the other a statement about it. */
.ieb__row {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  margin-top: 12px;
}

.ieb__actions {
  display: flex;
  align-items: center;
  gap: 16px;
}
</style>
