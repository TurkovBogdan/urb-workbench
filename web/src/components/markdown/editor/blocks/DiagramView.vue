<script setup lang="ts">
// Node view of a diagram: the picture by default, its source on demand.
//
// At rest the block is the renderer's own `DiagramBlock` — the same preview, the same fullscreen
// viewer on a double click — so a diagram looks the same in a field being edited and on a page
// being read. "Edit" in the top-right corner swaps the picture for its source in a plain
// monospace field; "Done", Esc or leaving the block swaps it back, redrawn.
//
// The source is written into the node on every keystroke, not on "Done": the page saves when the
// editor reports a change, and a person who types and then navigates away must not lose the edit.
import { computed, nextTick, onBeforeUnmount, onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { NodeViewWrapper, nodeViewProps } from '@tiptap/vue-3'
import { IconCheck, IconPencil } from '@tabler/icons-vue'

import DiagramBlock from '@/components/DiagramBlock.vue'

import { DIAGRAM_LANGUAGE } from '../../shared/contracts'

const props = defineProps(nodeViewProps)

const { t } = useI18n()

/** Indentation carries structure in mermaid (subgraphs), so Tab indents instead of leaving. */
const INDENT = '  '
/** The field is a few lines taller than its text, so the next line has room before it grows. */
const SPARE_ROWS = 1
const MIN_ROWS = 3

const source = computed(() => String(props.node.attrs.source ?? ''))

// The editor's editability is not reactive. Switching it (a task deleted while open) emits
// `update` — without a transaction — so that is the event it is re-read on.
const editable = ref(props.editor.isEditable)
const syncEditable = (): void => { editable.value = props.editor.isEditable }

const editing = ref(false)
const field = ref<HTMLTextAreaElement | null>(null)

const rows = computed(() => Math.max(MIN_ROWS, source.value.split('\n').length + SPARE_ROWS))

async function startEditing(): Promise<void> {
  if (!editable.value) return
  editing.value = true
  await nextTick()
  field.value?.focus()
}

/**
 * Back to the picture. An emptied source removes the block: an empty diagram draws nothing and
 * would only leave an empty fence in the body. `refocus` returns the caret to the document with
 * the block selected — when the person finished with the keyboard; a click elsewhere keeps focus
 * where the click put it.
 */
function finishEditing(refocus: boolean): void {
  if (!editing.value) return
  editing.value = false
  if (!source.value.trim()) {
    props.deleteNode()
    return
  }
  if (!refocus) return
  const pos = props.getPos()
  if (typeof pos === 'number') props.editor.chain().focus().setNodeSelection(pos).run()
}

// The document may refuse the change — the length limit filters the transaction out. The node then
// keeps its old source, `:value` does not change, so Vue never repaints the field and it would go on
// showing text that is not in the document. Put the field back, as the editor does for plain text.
function pushSource(area: HTMLTextAreaElement): void {
  props.updateAttributes({ source: area.value })
  if (area.value === source.value) return
  const caret = Math.min(area.selectionStart, source.value.length)
  area.value = source.value
  area.setSelectionRange(caret, caret)
}

function onInput(event: Event): void {
  pushSource(event.target as HTMLTextAreaElement)
}

function onKeydown(event: KeyboardEvent): void {
  if (event.key === 'Escape') {
    event.preventDefault()
    finishEditing(true)
    return
  }
  if (event.key === 'Tab' && !event.shiftKey) {
    event.preventDefault()
    const area = event.target as HTMLTextAreaElement
    area.setRangeText(INDENT, area.selectionStart, area.selectionEnd, 'end')
    pushSource(area)
  }
}

// Leaving the block ends editing; moving between the field and "Done" does not. Where focus went is
// checked a task later, not from the event: "Edit" holds focus when it is pressed and is unmounted
// by the very switch it causes, so its focusout reports focus going nowhere — a moment before the
// source field takes it.
function onFocusOut(event: FocusEvent): void {
  const block = event.currentTarget as HTMLElement
  setTimeout(() => {
    if (!block.contains(document.activeElement)) finishEditing(false)
  })
}

onMounted(() => {
  props.editor.on('update', syncEditable)
  const storage = props.editor.storage.diagram
  if (storage?.openNext) {
    storage.openNext = false
    void startEditing()
  }
})

onBeforeUnmount(() => {
  props.editor.off('update', syncEditable)
})
</script>

<template>
  <NodeViewWrapper
    class="diagram-node"
    :class="{ 'diagram-node--selected': props.selected && !editing, 'diagram-node--editing': editing }"
    contenteditable="false"
    @focusout="onFocusOut"
  >
    <template v-if="editing">
      <div class="diagram-node__bar">
        <span class="diagram-node__lang">{{ DIAGRAM_LANGUAGE }}</span>
        <VBtn variant="text" size="small" @click="finishEditing(true)">
          <template #prepend><IconCheck :size="16" /></template>
          {{ t('common.editor.diagram.done') }}
        </VBtn>
      </div>
      <textarea
        ref="field"
        class="diagram-node__source"
        :value="source"
        :rows="rows"
        :aria-label="t('common.editor.diagram.source')"
        spellcheck="false"
        @input="onInput"
        @keydown="onKeydown"
      />
    </template>

    <template v-else>
      <DiagramBlock :code="source" />
      <VBtn
        v-if="editable"
        variant="text"
        size="small"
        class="diagram-node__edit"
        @click="startEditing"
      >
        <template #prepend><IconPencil :size="16" /></template>
        {{ t('common.editor.diagram.edit') }}
      </VBtn>
    </template>
  </NodeViewWrapper>
</template>

<style scoped>
.diagram-node {
  position: relative;
  border-radius: var(--radius);
}

/* A selected block (Backspace would remove it) is outlined, like a selected pill. */
.diagram-node--selected {
  outline: 2px solid rgb(var(--v-theme-primary));
  outline-offset: 2px;
}

/* "Edit" sits at the right end of the picture's caption line ("double click — fullscreen"): on the
   block's right, but under the drawing rather than over it — a wide diagram fills its column, and
   a button on top would cover a box. It is quiet until the block is aimed at: a button on every
   diagram at once would be louder than the diagrams. 9px centres the button on the caption: the
   figure's 16px bottom margin and 12px padding, less half the button's extra height. */
.diagram-node__edit {
  position: absolute;
  bottom: 9px;
  right: 4px;
  opacity: 0;
  transition: opacity 0.15s ease;
}

.diagram-node:hover .diagram-node__edit,
.diagram-node:focus-within .diagram-node__edit,
.diagram-node--selected .diagram-node__edit { opacity: 1; }

@media (hover: none) {
  .diagram-node__edit { opacity: 1; }
}

/* In edit mode the block keeps the picture's place in the column: a frame of the same radius,
   the language on the left, "Done" on the right, the source below. */
.diagram-node--editing {
  margin: 16px 0;
  padding: 8px 12px 12px;
  border: 1px solid var(--accent);
  background: var(--surface);
}

.diagram-node__bar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 6px;
}

.diagram-node__lang {
  font-family: var(--font-mono);
  font-size: 11px;
  color: var(--text-faint);
}

.diagram-node__source {
  display: block;
  width: 100%;
  resize: vertical;
  padding: 8px 10px;
  font-family: var(--font-mono);
  font-size: 12px;
  line-height: 1.5;
  color: var(--text);
  background: var(--input-bg);
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  outline: none;
  tab-size: 2;
}

.diagram-node__source:focus { border-color: var(--accent); }
</style>
