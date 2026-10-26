<script setup lang="ts">
// Node view of an `IMAGE@` reference in a field with pictures — the picture the viewer draws,
// drawn again inside the document. The node is the same atom as a pill (`entityRef`): the caret
// steps over it, Backspace and Delete take it whole, and it prints back as its code.
//
// The markup is the viewer's (`span.md-image` holding the code's pill, the <img> put in once the
// preview says the file is there), so the states and their look come from the shared document
// stylesheet: pending — a quiet tile; shown — the picture; file — not a picture, the pill is a link;
// missing — the placeholder with the red pill.
//
// A click selects the picture, as an arrow key does — ProseMirror selects the atom itself; a double
// click, or Enter on the selected picture, opens it full screen with the rest of its gallery
// (`imageRuns`), in the editor's one viewer. The button in its corner copies its code. Taken with
// the pointer — a mouse moved 4 px, a finger held — the picture is dragged to another place
// (`pictureDrag.ts`). A right click selects it and opens its menu (`PictureMenu.vue`), with "delete
// from the text" here; Shift keeps the browser's own menu.
import { computed, inject, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { NodeViewWrapper, nodeViewProps } from '@tiptap/vue-3'
import { useClipboard } from '@/composables/useClipboard'
import { usePreviews } from '@/stores/preview'
import { refIsMissing } from '../../../shared/contracts'
import EntityPreviewPopup from '../../../shared/EntityPreviewPopup.vue'
import { fileKindClass } from '../../../shared/fileKind'
import PictureMenu from '../../../shared/PictureMenu.vue'
import { isSizeless, markNotPicture, notePicture, pictureState, touchGalleries } from '../../../shared/pictures'
import { imageRuns, inlineChildren } from './imageRuns'
import { removePicture } from './pictureMove'
import { OPEN_PICTURE, OPEN_PICTURE_EVENT } from './pictureViewer'

const props = defineProps(nodeViewProps)

const { t } = useI18n()
const { copy, isCopied } = useClipboard()
const previews = usePreviews()
const openPicture = inject(OPEN_PICTURE, null)

const code = computed(() => String(props.node.attrs.code ?? ''))
const record = computed(() => previews.get(code.value))
const state = computed(() => pictureState(record.value))
const missing = computed(() => refIsMissing(code.value, record.value?.error?.code))
// Seen only when the file is not a picture: the pill is then a link, with its kind's glyph.
const kindClass = computed(() => fileKindClass(code.value, record.value))
const link = computed(() => record.value?.link || undefined)

// Every picture of a document mounts in the same tick, so the store gathers them into one request.
watch(code, (value) => previews.ensure([value]), { immediate: true })

// The gallery is laid out by the editor's plugin, which does not see this view change its state.
watch(state, () => touchGalleries(), { flush: 'post' })

const sizeless = ref(false)

function onLoad(event: Event): void {
  const image = event.target as HTMLImageElement
  notePicture(code.value, image.naturalWidth, image.naturalHeight)
  sizeless.value = isSizeless(image)
}

/** The codes of the pictures shown in this one's gallery, in order. */
function gallery(): string[] {
  const pos = props.getPos()
  if (typeof pos !== 'number') return []
  const at = props.editor.state.doc.resolve(pos)
  const index = at.index()
  const run = imageRuns(inlineChildren(at.parent)).find((one) => one.indexes.includes(index))
  return (run?.codes ?? [code.value]).filter((one) => pictureState(previews.get(one)) === 'shown')
}

function open(): void {
  if (state.value === 'shown' && link.value) openPicture?.(code.value, gallery(), () => props.getPos())
}

const wrapper = ref<{ $el: HTMLElement } | null>(null)

onMounted(() => wrapper.value?.$el.addEventListener(OPEN_PICTURE_EVENT, open))
onBeforeUnmount(() => wrapper.value?.$el.removeEventListener(OPEN_PICTURE_EVENT, open))

const copied = computed(() => isCopied(code.value))
const copyLabel = computed(() => (copied.value ? t('common.action.copied') : t('common.action.copy_code')))

// The pill is a link to the file — what is left when the file is not a picture, or gone.
function onPillClick(event: MouseEvent): void {
  event.preventDefault()
  if (link.value) window.open(link.value, '_blank', 'noopener')
}

const pill = ref<HTMLElement | null>(null)
const popup = ref<InstanceType<typeof EntityPreviewPopup> | null>(null)

// A pointer crossing a pill with a button held is selecting text, not asking what the pill is.
function onPointerEnter(event: MouseEvent): void {
  if (event.buttons || !pill.value) return
  popup.value?.hover(pill.value, code.value)
}

function onPointerLeave(): void {
  popup.value?.leave()
}

// ── Menu ──────────────────────────────────────────────────────────────────────
// The right click selects the picture first: the outline then says which one the menu acts on, as
// a list row's mark does. Whether it may leave the text is read at that moment — a field turns
// read-only when its holder is deleted.
const menu = ref<InstanceType<typeof PictureMenu> | null>(null)
const removable = ref(false)

function onContextMenu(event: MouseEvent): void {
  if (state.value !== 'shown' || event.shiftKey) return
  const pos = props.getPos()
  if (typeof pos === 'number') props.editor.commands.setNodeSelection(pos)
  removable.value = props.editor.isEditable
  menu.value?.openAt(event)
}

// The file this picture showed is deleted: the picture leaves the text too, rather than stand there
// as a red "no file". Its other mentions stay and turn red — the dialog said so.
function onFileDeleted(): void {
  if (removable.value) removeFromText()
}

function removeFromText(): void {
  const pos = props.getPos()
  if (typeof pos !== 'number') return
  const tr = removePicture(props.editor.state, pos)
  if (!tr) return
  props.editor.view.dispatch(tr)
  props.editor.commands.focus()
}
</script>

<template>
  <!-- `selected` is a real NodeSelection: the node is an atom, so what is highlighted is exactly
       what Backspace would remove. -->
  <NodeViewWrapper
    ref="wrapper"
    as="span"
    class="md-image"
    :class="[`md-image--${state}`, { 'md-image--selected': props.selected, 'md-image--sizeless': sizeless }]"
    @contextmenu="onContextMenu"
  >
    <img
      v-if="state === 'shown' && link"
      :src="link"
      :alt="record?.title || code"
      decoding="async"
      draggable="false"
      @error="markNotPicture(link)"
      @load="onLoad"
      @dblclick="open"
    >
    <!-- A button inside a node view: Tiptap keeps its events from ProseMirror, and `mousedown` is
         held back so the press neither moves the caret nor takes the focus from the field. -->
    <button
      v-if="state === 'shown' && link"
      type="button"
      class="md-image__copy"
      :class="{ 'md-image__copy--copied': copied }"
      :aria-label="copyLabel"
      :title="copyLabel"
      @mousedown.prevent
      @click.prevent.stop="copy(code)"
    />
    <span
      ref="pill"
      class="md-ref md-ref--image"
      :class="[kindClass, { 'md-ref--missing': missing }]"
      @mouseenter="onPointerEnter"
      @mouseleave="onPointerLeave"
    >
      <a
        class="md-ref-label"
        :href="link"
        draggable="false"
        @click="onPillClick"
        @auxclick="onPillClick"
      >{{ code }}</a>
    </span>
    <EntityPreviewPopup ref="popup" />
    <PictureMenu
      v-if="state === 'shown'"
      ref="menu"
      :code="code"
      :remove="removable ? removeFromText : undefined"
      @open="open"
      @deleted="onFileDeleted"
    />
  </NodeViewWrapper>
</template>

<style scoped>
/* Only what the viewer does not have: the selection. Shape, states and sizes come from the shared
   document stylesheet.

   The picture stays selectable as a whole: with `user-select: none` a selection dragged with the
   mouse could not end on a picture — the browser found no place for its end there, and the whole
   selection collapsed to where it started. A picture inside a selection says so by its outline
   (`--selected`), as it does under the keyboard; the browser's own tint over it is turned off, so
   the two look the same. */
.md-image > img::selection {
  background: transparent;
}

/* A finger held on a picture takes it to drag; Safari on iOS would bring up the picture's own menu
   for the same hold. */
.md-image > img {
  -webkit-touch-callout: none;
}

.md-ref-label {
  color: inherit;
  text-decoration: none;
  cursor: pointer;
}

/* On the slot, not the picture: the slot rounds and cuts the picture, an outline on it would be cut
   away too. */
.md-image--shown.md-image--selected {
  outline: 2px solid rgb(var(--v-theme-primary));
  outline-offset: 2px;
}

.md-image--selected > .md-ref {
  background: color-mix(in srgb, rgb(var(--md-ref-color)) 22%, transparent);
  border-color: rgb(var(--md-ref-color));
}
</style>
