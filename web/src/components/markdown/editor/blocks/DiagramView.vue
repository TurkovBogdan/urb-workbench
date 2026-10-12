<script setup lang="ts">
// Node view of a diagram: the picture.
//
// The block is the renderer's own `DiagramBlock` — the same preview, the same fullscreen viewer on
// a double click — so a diagram looks the same in a field being edited and on a page being read.
// "Edit" does not open anything here: it turns the block into its source, the editor's code block
// (see diagram.ts), which turns back into this picture when the caret leaves it.
import { onBeforeUnmount, onMounted, ref, computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { NodeViewWrapper, nodeViewProps } from '@tiptap/vue-3'
import { IconPencil } from '@tabler/icons-vue'

import DiagramBlock from '@/components/DiagramBlock.vue'

const props = defineProps(nodeViewProps)

const { t } = useI18n()

const source = computed(() => String(props.node.attrs.source ?? ''))

// The editor's editability is not reactive. Switching it (a task deleted while open) emits
// `update` — without a transaction — so that is the event it is re-read on.
const editable = ref(props.editor.isEditable)
const syncEditable = (): void => { editable.value = props.editor.isEditable }

// A field without code blocks has nowhere to edit the source in; the picture stays a picture.
const canEdit = computed(() => editable.value && Boolean(props.editor.schema.nodes.codeBlock))

function edit(): void {
  const pos = props.getPos()
  if (typeof pos === 'number') props.editor.chain().focus().editDiagram(pos).run()
}

onMounted(() => props.editor.on('update', syncEditable))
onBeforeUnmount(() => props.editor.off('update', syncEditable))
</script>

<template>
  <NodeViewWrapper
    class="diagram-node"
    :class="{ 'diagram-node--selected': props.selected }"
    contenteditable="false"
  >
    <DiagramBlock :code="source">
      <!-- On the picture's caption line, at its right end (DiagramBlock's `actions`): under the
           drawing rather than over it — a wide diagram fills its column, and a button on top would
           cover a box — and inside the picture's width however narrow it is. -->
      <template v-if="canEdit" #actions>
        <VBtn
          variant="text"
          size="x-small"
          class="diagram-node__edit"
          @click="edit"
        >
          <template #prepend><IconPencil :size="14" /></template>
          {{ t('common.editor.diagram.edit') }}
        </VBtn>
      </template>
    </DiagramBlock>
  </NodeViewWrapper>
</template>

<style scoped>
.diagram-node {
  position: relative;
  border-radius: var(--radius);
}

/* No frame in the editor — neither the picture's hover frame (DiagramBlock) nor one for the
   selected block. Every block of the document already has its handle beside it, and a frame
   appearing under the pointer on each diagram only made the column flicker. Doubled class: the
   rule outranks DiagramBlock's own `.diagram:hover` whatever order the styles load in. */
.diagram-node.diagram-node :deep(.diagram) {
  border-color: transparent;
  background: none;
}

/* The block takes the column's width, the picture keeps its own size inside it (aligned by the
   `--diagram-justify` DiagramBlock sets): a double click anywhere on the block opens the viewer,
   not only on the drawing, and the caption line with "Edit" runs to the column's edge. */
.diagram-node.diagram-node :deep(figure.diagram) {
  width: 100%;
  margin-left: 0;
  margin-right: 0;
}

/* "Edit" is quiet until the block is aimed at: a button on every diagram at once would be louder
   than the diagrams. */
.diagram-node__edit {
  opacity: 0;
  transition: opacity 0.15s ease;
}

.diagram-node:hover .diagram-node__edit,
.diagram-node:focus-within .diagram-node__edit,
.diagram-node--selected .diagram-node__edit { opacity: 1; }

@media (hover: none) {
  .diagram-node__edit { opacity: 1; }
}
</style>
