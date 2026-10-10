<script setup lang="ts">
// Node view of an entity reference. The pill the renderer draws, drawn again — but as a Vue
// component inside the document, so it can do what a static pill cannot: be replaced in place.
//
// Classes are the renderer's own (`md-ref`, `md-ref--<type>`, `md-ref-label`) and the shape comes
// from `markdown/shared/document.css`: the pill has to look the same in both zones, and the only
// way to guarantee that is to give both the same markup and one stylesheet.
//
// A click on the pill opens the entity, as in the viewer — the owner's call: a reference is read
// far more often than it is re-pointed. Re-pointing has its own door, the pencil on the right
// edge (or Enter on a selected pill), which turns the label into a field holding the code.
import { computed, nextTick, onBeforeUnmount, onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRouter } from 'vue-router'
import { NodeViewWrapper, nodeViewProps } from '@tiptap/vue-3'
import { IconPencil } from '@tabler/icons-vue'
import { parseRefCode, refPath } from '../../shared/contracts'
import { REF_EDIT_EVENT } from './entityRef'

const props = defineProps(nodeViewProps)

const { t } = useI18n()
const router = useRouter()

const code = computed(() => String(props.node.attrs.code ?? ''))
const typeClass = computed(() => `md-ref--${code.value.split('@')[0].toLowerCase()}`)
const href = computed(() => refPath(code.value))

// The editor's editability is not reactive. Switching it (a task deleted while open) emits
// `update` — without a transaction — so that is the event it is re-read on.
const editable = ref(props.editor.isEditable)
const syncEditable = (): void => { editable.value = props.editor.isEditable }

const editing = ref(false)
const draft = ref('')
const invalid = ref(false)
const field = ref<HTMLInputElement | null>(null)
const wrapper = ref<{ $el: HTMLElement } | null>(null)

// The field is exactly as wide as the code it holds, in the pill's own monospace: opening it must
// not re-wrap the line the pill sits in.
const fieldWidth = computed(() => `${Math.max(draft.value.length, code.value.length)}ch`)

function open(event: MouseEvent): void {
  event.preventDefault()
  if (editing.value) return
  if (event.ctrlKey || event.metaKey || event.shiftKey || event.button === 1) {
    window.open(href.value, '_blank', 'noopener')
    return
  }
  router.push(href.value)
}

async function startEditing(): Promise<void> {
  if (!editable.value || editing.value) return
  draft.value = code.value
  invalid.value = false
  editing.value = true
  await nextTick()
  field.value?.focus()
  field.value?.select()
}

/**
 * Back to the pill. Only a whole code of the vocabulary replaces the old one; anything else leaves
 * the pill as it was — a reference is never turned into a half-code or plain text from here.
 * `refocus` returns the caret to the document with the pill selected, for the keyboard path.
 */
function finishEditing(commit: boolean, refocus: boolean): void {
  if (!editing.value) return
  editing.value = false
  invalid.value = false
  const next = commit ? parseRefCode(draft.value) : null
  if (next && next !== code.value) props.updateAttributes({ code: next })
  if (!refocus) return
  const pos = props.getPos()
  if (typeof pos === 'number') props.editor.chain().focus().setNodeSelection(pos).run()
}

function onKeydown(event: KeyboardEvent): void {
  if (event.key === 'Escape') {
    event.preventDefault()
    finishEditing(false, true)
    return
  }
  if (event.key !== 'Enter') return
  event.preventDefault()
  if (parseRefCode(draft.value)) finishEditing(true, true)
  else invalid.value = true
}

function onInput(): void {
  invalid.value = false
}

onMounted(() => {
  props.editor.on('update', syncEditable)
  wrapper.value?.$el.addEventListener(REF_EDIT_EVENT, startEditing)
})

onBeforeUnmount(() => {
  props.editor.off('update', syncEditable)
  wrapper.value?.$el.removeEventListener(REF_EDIT_EVENT, startEditing)
})
</script>

<template>
  <!-- `selected` is a real NodeSelection here because the node is an atom — no caret can land
       inside it, so the highlight never lies about what delete would remove. -->
  <NodeViewWrapper
    ref="wrapper"
    as="span"
    class="md-ref md-ref--editable"
    :class="[typeClass, { 'md-ref--selected': props.selected, 'md-ref--editing': editing, 'md-ref--invalid': invalid }]"
    :title="editing ? undefined : code"
  >
    <input
      v-if="editing"
      ref="field"
      v-model="draft"
      class="md-ref-field"
      :style="{ width: fieldWidth }"
      :aria-label="t('common.editor.ref.field')"
      :aria-invalid="invalid"
      :title="invalid ? t('common.editor.ref.invalid') : undefined"
      spellcheck="false"
      autocomplete="off"
      @keydown="onKeydown"
      @input="onInput"
      @blur="finishEditing(true, false)"
    >
    <a
      v-else
      class="md-ref-label"
      :href="href"
      draggable="false"
      @click="open"
      @auxclick="open"
    >{{ code }}</a>
    <button
      v-if="editable && !editing"
      type="button"
      class="md-ref-edit"
      tabindex="-1"
      :title="t('common.editor.ref.edit')"
      :aria-label="t('common.editor.ref.edit')"
      @mousedown.prevent
      @click.stop="startEditing"
    >
      <IconPencil :size="11" :stroke-width="2.2" />
    </button>
  </NodeViewWrapper>
</template>

<style scoped>
/* Only what the viewer does not and cannot have: selection, the edit door and the edit field. The
   pill's shape, colour, glyph and size come from the shared document stylesheet — duplicating them
   here would start a second truth about what an entity reference looks like. */
.md-ref {
  position: relative;
  user-select: none;
}

.md-ref-label {
  color: inherit;
  text-decoration: none;
  cursor: pointer;
}

.md-ref--selected {
  background: color-mix(in srgb, rgb(var(--v-theme-primary)) 22%, transparent);
  border-color: rgb(var(--v-theme-primary));
}

/* The pencil sits over the right end of the pill rather than beside it: appearing on hover, it must
   not push the rest of the line, and the pill keeps the width the viewer gives it. */
.md-ref-edit {
  position: absolute;
  top: 50%;
  right: -1px;
  display: grid;
  place-items: center;
  width: 1.7em;
  height: calc(100% + 2px);
  padding: 0;
  border: 1px solid color-mix(in srgb, rgb(var(--v-theme-primary)) 45%, transparent);
  border-radius: 9px;
  color: rgb(var(--v-theme-primary));
  background: rgb(var(--v-theme-surface));
  transform: translateY(-50%);
  opacity: 0;
  pointer-events: none;
  cursor: pointer;
  transition: opacity 0.12s ease;
}

.md-ref:hover .md-ref-edit,
.md-ref--selected .md-ref-edit {
  opacity: 1;
  pointer-events: auto;
}

.md-ref-edit:hover {
  background: color-mix(in srgb, rgb(var(--v-theme-primary)) 14%, rgb(var(--v-theme-surface)));
}

.md-ref-field {
  padding: 0;
  margin: 0;
  border: 0;
  outline: none;
  background: transparent;
  color: inherit;
  font: inherit;
  line-height: inherit;
  user-select: text;
}

.md-ref--editing {
  border-color: rgb(var(--v-theme-primary));
}

.md-ref--invalid {
  color: rgb(var(--v-theme-error));
  background: color-mix(in srgb, rgb(var(--v-theme-error)) 9%, transparent);
  border-color: rgb(var(--v-theme-error));
}
</style>
