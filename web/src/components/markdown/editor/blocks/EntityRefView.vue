<script setup lang="ts">
// Node view of an entity reference. The pill the renderer draws, drawn again — but as a Vue
// component inside the document, which is the point of the exercise: a custom block here is an
// ordinary component and can hold anything the rest of the interface holds.
//
// Classes are the renderer's own (`md-ref`, `md-ref-label`) and the shape comes from
// `markdown/shared/document.css`: the pill has to look the same in both zones, and the only way
// to guarantee that is to give both the same markup and one stylesheet. A `span` rather than the
// renderer's `a` — inside an editable document a click places the caret, it does not navigate.
import { computed } from 'vue'
import { NodeViewWrapper, nodeViewProps } from '@tiptap/vue-3'

const props = defineProps(nodeViewProps)

const code = computed(() => String(props.node.attrs.code ?? ''))
// Same transient label as the renderer: the hash is opaque in prose, so a short prefix stands
// in until a resolved title replaces it. Resolving titles is the next step, not this one.
const label = computed(() => code.value.split('@')[1]?.slice(0, 6) ?? '')
</script>

<template>
  <!-- `selected` is a real NodeSelection here because the node is an atom — no caret can land
       inside it, so the highlight never lies about what delete would remove. -->
  <NodeViewWrapper
    as="span"
    class="md-ref"
    :class="{ 'md-ref--selected': props.selected }"
    :title="code"
  >
    <span class="md-ref-label">{{ label }}</span>
  </NodeViewWrapper>
</template>

<style scoped>
/* Только то, чего у просмотра нет и быть не может: состояние выделения узла. Форма, цвет,
   глиф и кегль пилюли приходят из общего файла документа — дублировать их здесь значило бы
   завести вторую правду о том, как выглядит ссылка на сущность. */
.md-ref {
  cursor: default;
  user-select: none;
}

.md-ref--selected {
  background: color-mix(in srgb, rgb(var(--v-theme-primary)) 22%, transparent);
  border-color: rgb(var(--v-theme-primary));
}
</style>
