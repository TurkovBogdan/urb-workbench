<script setup lang="ts">
// Node view of an entity reference — the pill the renderer draws, drawn again as a Vue component
// inside the document, so it can open the hover card and navigate like the viewer's.
//
// Classes are the renderer's own (`md-ref`, `md-ref--<type>`, `md-ref-label`) and the shape comes
// from `markdown/shared/document.css`: the pill has to look the same in both zones, and the only
// way to guarantee that is to give both the same markup and one stylesheet.
//
// A pill has no edit mode — the owner's call: a reference is read, not re-pointed. A wrong one is
// deleted (Backspace/Delete on the selected pill) and typed or pasted again. A click opens the
// entity, as in the viewer.
import { computed, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { NodeViewWrapper, nodeViewProps } from '@tiptap/vue-3'
import { usePreviews } from '@/stores/preview'
import { refIsFile, refIsMissing, refPath } from '../../../shared/contracts'
import EntityPreviewPopup from '../../../shared/EntityPreviewPopup.vue'
import { fileKindClass } from '../../../shared/fileKind'

const props = defineProps(nodeViewProps)

const router = useRouter()
const previews = usePreviews()

const code = computed(() => String(props.node.attrs.code ?? ''))
const typeClass = computed(() => `md-ref--${code.value.split('@')[0].toLowerCase()}`)
// The preview knows every type's page; before it comes, what the code alone can tell (or nothing).
const href = computed(() => previews.get(code.value)?.link || refPath(code.value) || undefined)
const missing = computed(() => refIsMissing(code.value, previews.get(code.value)?.error?.code))
const kindClass = computed(() => fileKindClass(code.value, previews.get(code.value)))

// Every pill of a document mounts in the same tick, so the store gathers them into one request.
watch(code, (value) => previews.ensure([value]), { immediate: true })

const wrapper = ref<{ $el: HTMLElement } | null>(null)
const popup = ref<InstanceType<typeof EntityPreviewPopup> | null>(null)

// A pointer crossing a pill with a button held is selecting text, not asking what the pill is.
function onPointerEnter(event: MouseEvent): void {
  if (event.buttons || !wrapper.value) return
  popup.value?.hover(wrapper.value.$el, code.value)
}

function onPointerLeave(): void {
  popup.value?.leave()
}

function open(event: MouseEvent): void {
  event.preventDefault()
  const target = href.value
  if (!target) return
  if (refIsFile(code.value) || event.ctrlKey || event.metaKey || event.shiftKey || event.button === 1) {
    window.open(target, '_blank', 'noopener')
    return
  }
  router.push(target)
}
</script>

<template>
  <!-- `selected` is a real NodeSelection here because the node is an atom — no caret can land
       inside it, so the highlight never lies about what delete would remove. -->
  <NodeViewWrapper
    ref="wrapper"
    as="span"
    class="md-ref md-ref--editable"
    :class="[typeClass, kindClass, { 'md-ref--selected': props.selected, 'md-ref--missing': missing }]"
    @mouseenter="onPointerEnter"
    @mouseleave="onPointerLeave"
  >
    <a
      class="md-ref-label"
      :href="href"
      draggable="false"
      @click="open"
      @auxclick="open"
    >{{ code }}</a>
    <EntityPreviewPopup ref="popup" />
  </NodeViewWrapper>
</template>

<style scoped>
/* Only what the viewer does not have: the selection. The pill's shape, colour, glyph and size come
   from the shared document stylesheet — duplicating them here would start a second truth about
   what an entity reference looks like. */
.md-ref {
  user-select: none;
}

.md-ref-label {
  color: inherit;
  text-decoration: none;
  cursor: pointer;
}

/* In the pill's own colour (`--md-ref-color`, `shared/document.css`): a selected file stays green. */
.md-ref--selected {
  background: color-mix(in srgb, rgb(var(--md-ref-color)) 22%, transparent);
  border-color: rgb(var(--md-ref-color));
}
</style>
