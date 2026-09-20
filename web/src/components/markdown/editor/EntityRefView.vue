<script setup lang="ts">
// Node view of an entity reference. The pill the renderer draws, drawn again — but as a Vue
// component inside the document, which is the point of the exercise: a custom block here is an
// ordinary component and can hold anything the rest of the interface holds.
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
  <NodeViewWrapper as="span" class="ref" :class="{ 'ref--selected': props.selected }" :title="code">
    <span class="ref__label">{{ label }}</span>
  </NodeViewWrapper>
</template>

<style scoped>
.ref {
  display: inline-flex;
  align-items: center;
  gap: 3px;
  font-family: var(--font-mono);
  font-size: 0.78em;
  line-height: 1;
  padding: 1.5px 6px 1.5px 5px;
  margin: 0 1px;
  border-radius: 9px;
  color: rgb(var(--v-theme-primary));
  background: color-mix(in srgb, rgb(var(--v-theme-primary)) 9%, transparent);
  border: 1px solid color-mix(in srgb, rgb(var(--v-theme-primary)) 22%, transparent);
  white-space: nowrap;
  vertical-align: baseline;
  cursor: default;
  user-select: none;
}

.ref::before {
  content: "";
  flex: none;
  width: 1cap;
  height: 1cap;
  background: currentColor;
  border-radius: 2px;
  opacity: 0.55;
}

.ref--selected {
  background: color-mix(in srgb, rgb(var(--v-theme-primary)) 22%, transparent);
  border-color: rgb(var(--v-theme-primary));
}
</style>
