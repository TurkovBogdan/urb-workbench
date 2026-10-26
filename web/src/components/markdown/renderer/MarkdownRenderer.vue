<script setup lang="ts">
import { computed, getCurrentInstance, h, nextTick, onBeforeUnmount, onMounted, ref, render, watch, watchEffect } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRouter } from 'vue-router'
import type { PreviewRecord } from '@/api/lookup'
import CodeBlock from '@/components/CodeBlock.vue'
import DiagramBlock from '@/components/DiagramBlock.vue'
import ImageGallery from '@/components/files/ImageGallery.vue'
import { useClipboard } from '@/composables/useClipboard'
import { useAfterRouteTransition } from '@/composables/useRouteTransition'
import { usePreviews } from '@/stores/preview'
import { useSettingsStore } from '@/stores/settings'
import { refIsMissing } from '../shared/contracts'
import EntityPreviewPopup from '../shared/EntityPreviewPopup.vue'
import { fileKindClass, setFileKindClass } from '../shared/fileKind'
import PictureMenu from '../shared/PictureMenu.vue'
import {
  galleryVersion, isSizeless, layOutGallery, markNotPicture, notePicture, PICTURE_STATES, pictureCode,
  pictureState, placeRowBreaks,
} from '../shared/pictures'
import { renderMarkdown, type HeadingAnchor } from './render'

// The body is the component's face, the hover card its sibling: attributes a parent sets (a class,
// a style) belong on the body.
defineOptions({ inheritAttrs: false })

const { t } = useI18n()
const router = useRouter()
const settings = useSettingsStore()
const previews = usePreviews()
const { copy, isCopied } = useClipboard()

const props = defineProps<{
  text: string
  compact?: boolean
  // A whole document, not a caption under a field: parsing and laying out such a body holds the
  // main thread for tens of milliseconds, and if that landed on a page transition it would eat
  // the animation. A body marked this way waits for the transition to end; everything else
  // renders immediately.
  heavy?: boolean
  // Render Markdown images as <img> (off by default: the agent chat strips them).
  allowImages?: boolean
  // Treat single newlines as <br> — preserves line breaks of plain-text email bodies.
  breaks?: boolean
}>()

const emit = defineEmits<{
  imageClick: [src: string]
  // The body's outline: headings with their assigned `id`. Emitted as an event rather than via
  // expose — the consumer (side navigation) needs a ready list, not access into the renderer.
  headings: [items: HeadingAnchor[]]
}>()

// Empty text while the transition runs is the deferral itself: parsing does not start, the
// outline arrives together with the body, and no consumer learns anything about the wait beyond
// the body being empty for now.
const settled = useAfterRouteTransition()

const source = computed(() => (props.heavy && !settled.value ? '' : props.text))

const rendered = computed(() => renderMarkdown(source.value, {
  breaks: props.breaks ?? false,
  allowImages: props.allowImages ?? false,
}))

const html = computed(() => rendered.value.html)

watch(() => rendered.value.headings, (items) => emit('headings', items), { immediate: true })

// Code blocks are not part of the HTML: the parser leaves an empty slot for each one and the
// real component is mounted into it here, so a body gets highlighting, a copy button and a
// language badge. A one-liner takes the compact variant — a command reads as a chip, not as a
// panel with a header. A `mermaid` fence is a diagram instead: the same slot, another component.
const DIAGRAM_LANGUAGE = 'mermaid'

const body = ref<HTMLElement | null>(null)
const appContext = getCurrentInstance()?.appContext ?? null
let mountedSlots: HTMLElement[] = []

function unmountCodeBlocks() {
  for (const slot of mountedSlots) render(null, slot)
  mountedSlots = []
}

// A repeat call on the same body is an update, not a rebuild: `render` into the same slot with the
// same component patches the props, so a change of the line-number setting reaches the blocks
// without re-highlighting. The slot list is collected afresh, or duplicates would pile up in it on
// every call.
function mountCodeBlocks() {
  const container = body.value
  if (!container) return
  mountedSlots = []
  container.querySelectorAll<HTMLElement>('.md-code-slot').forEach((slot) => {
    const block = rendered.value.codeBlocks[Number(slot.dataset.codeIndex)]
    if (!block) return
    const code = block.code.replace(/\n$/, '')
    const isOneLiner = !block.code.trim().includes('\n')
    const vnode = block.language === DIAGRAM_LANGUAGE
      ? h(DiagramBlock, { code })
      : h(CodeBlock, {
          code,
          lang: block.language || undefined,
          // A one-liner is a command chip regardless of the chosen variant: that is about the
          // content, not the styling.
          variant: isOneLiner ? 'compact' : settings.typography.codeVariant,
          showLineNumbers: settings.typography.codeLineNumbers,
        })
    vnode.appContext = appContext
    render(vnode, slot)
    mountedSlots.push(slot)
  })
}

watch(
  () => [settings.typography.codeVariant, settings.typography.codeLineNumbers],
  () => mountCodeBlocks(),
)

// v-html replaces the container's children, so the previous instances are unmounted first —
// while their slots (detached by then or not) are still known here. The blocks are watched too:
// a slot is empty in the HTML, so a text that changed only inside a fence leaves `html` equal
// and would keep the old block on screen.
watch([html, () => rendered.value.codeBlocks], () => {
  unmountCodeBlocks()
  nextTick(mountCodeBlocks)
})

onMounted(mountCodeBlocks)
onBeforeUnmount(unmountCodeBlocks)

// The pills of a drawn body ask for their previews at once, all in one request, so the hover card
// finds its record already there. The store sends only the codes it does not hold yet.
const pillCodes = ref<string[]>([])

function pills(): HTMLElement[] {
  return [...(body.value?.querySelectorAll<HTMLElement>('.md-ref[data-ref]') ?? [])]
}

function askForPreviews() {
  pillCodes.value = pills().map((pill) => pill.dataset.ref ?? '')
  previews.ensure(pillCodes.value)
}

watch(html, () => nextTick(askForPreviews))
onMounted(askForPreviews)

// A pill takes its address and its state from its preview: the HTML carries only what the code
// alone can tell — a stage or a note learns its task's page here, a file the glyph of its kind, and
// a code that leads nowhere is marked as such, once the preview comes.
watchEffect(() => {
  const records = new Map(pillCodes.value.map((code) => [code, previews.get(code)]))
  for (const pill of pills()) {
    const code = pill.dataset.ref ?? ''
    const record = records.get(code)
    if (record?.link) pill.setAttribute('href', record.link)
    pill.classList.toggle('md-ref--missing', refIsMissing(code, record?.error?.code))
    setFileKindClass(pill, fileKindClass(code, record))
  }
  for (const slot of imageSlots()) {
    const code = slot.querySelector<HTMLElement>('.md-ref[data-ref]')?.dataset.ref ?? ''
    paintImage(slot, code, records.get(code))
  }
  // Read here so a picture that loads lays its gallery out again with its own proportions.
  void galleryVersion.value
  for (const gallery of body.value?.querySelectorAll<HTMLElement>('.md-gallery') ?? []) {
    const tiles = [...gallery.querySelectorAll<HTMLElement>('.md-image')]
    placeRowBreaks(gallery, tiles)
    layOutGallery(tiles)
  }
}, { flush: 'post' })

// ── `IMAGE@` pictures ─────────────────────────────────────────────────────────
// The parser leaves each picture its pill (`span.md-image`); the <img> goes in here, at the
// preview's address once the preview says the file is there. Which state a picture is in is the
// same answer the editor gives (`shared/pictures.ts`).
function imageSlots(): HTMLElement[] {
  return [...(body.value?.querySelectorAll<HTMLElement>('.md-image') ?? [])]
}

function paintImage(slot: HTMLElement, code: string, record: PreviewRecord | undefined): void {
  const state = pictureState(record)
  for (const one of PICTURE_STATES) slot.classList.toggle(`md-image--${one}`, one === state)
  const existing = slot.querySelector('img')
  if (state !== 'shown' || !record) {
    existing?.remove()
    slot.querySelector('.md-image__copy')?.remove()
    return
  }
  paintCopyButton(slot, code)
  const image = existing ?? slot.insertBefore(document.createElement('img'), slot.firstChild)
  if (existing) {
    if (image.getAttribute('src') !== record.link) image.setAttribute('src', record.link)
    return
  }
  image.alt = record.title || code
  image.decoding = 'async'
  image.addEventListener('error', () => markNotPicture(image.getAttribute('src') ?? ''), { once: true })
  image.addEventListener('load', () => {
    notePicture(code, image.naturalWidth, image.naturalHeight)
    slot.classList.toggle('md-image--sizeless', isSizeless(image))
  }, { once: true })
  image.setAttribute('src', record.link)
}

// The button in a shown picture's corner copies its code (`.md-image__copy`, the editor's markup).
// Read inside the painting effect: the copied mark follows the clipboard without a watcher of its own.
function paintCopyButton(slot: HTMLElement, code: string): void {
  const button = slot.querySelector<HTMLButtonElement>('.md-image__copy') ?? slot.appendChild(document.createElement('button'))
  button.type = 'button'
  button.className = 'md-image__copy'
  const copied = isCopied(code)
  button.classList.toggle('md-image__copy--copied', copied)
  const label = copied ? t('common.action.copied') : t('common.action.copy_code')
  button.title = label
  button.setAttribute('aria-label', label)
}

// A click on a picture opens it full screen, with the rest of its gallery to page through — the
// shown pictures of the gallery by their codes; the viewer reads each from its preview.
const lightbox = ref<string | null>(null)
const lightboxCodes = ref<string[]>([])

function openPicture(image: HTMLImageElement): void {
  const gallery = image.closest('.md-gallery') ?? image
  lightboxCodes.value = [...gallery.querySelectorAll<HTMLElement>('.md-image--shown')].map(pictureCode)
  lightbox.value = image.parentElement ? pictureCode(image.parentElement) : null
}

// A right click on a shown picture opens its menu (`PictureMenu.vue`). The pictures are plain HTML,
// so the body keeps one menu and aims it at the picture clicked; the text here is read, not edited,
// so the menu has no "delete from the text". Shift keeps the browser's own menu.
const pictureMenu = ref<InstanceType<typeof PictureMenu> | null>(null)
const menuPicture = ref<HTMLImageElement | null>(null)
const menuCode = computed(() => (menuPicture.value?.parentElement ? pictureCode(menuPicture.value.parentElement) : ''))

function onContextMenu(event: MouseEvent): void {
  if (event.shiftKey) return
  const slot = (event.target as HTMLElement).closest<HTMLElement>('.md-image--shown')
  const picture = slot?.querySelector<HTMLImageElement>(':scope > img')
  if (!picture) return
  menuPicture.value = picture
  pictureMenu.value?.openAt(event)
}

function openMenuPicture(): void {
  if (menuPicture.value) openPicture(menuPicture.value)
}

// The pills are plain HTML, so the body keeps one hover card and points it at whichever pill the
// pointer is on. `mouseover`/`mouseout` bubble, unlike `mouseenter`; moves between a pill and its
// own label are not a leave.
const popup = ref<InstanceType<typeof EntityPreviewPopup> | null>(null)

function pillOf(target: EventTarget | null): HTMLElement | null {
  return target instanceof Element ? target.closest<HTMLElement>('.md-ref[data-ref]') : null
}

// A pointer crossing a pill with a button held is selecting text, not asking what the pill is.
function onPointerOver(event: MouseEvent) {
  if (event.buttons) return
  const pill = pillOf(event.target)
  if (pill) popup.value?.hover(pill, pill.dataset.ref ?? '')
}

function onPointerOut(event: MouseEvent) {
  const pill = pillOf(event.target)
  if (pill && pill !== pillOf(event.relatedTarget)) popup.value?.leave()
}

function onClick(event: MouseEvent) {
  const copyButton = (event.target as HTMLElement).closest<HTMLElement>('.md-image__copy')
  if (copyButton) {
    event.preventDefault()
    const slot = copyButton.closest<HTMLElement>('.md-image')
    if (slot) void copy(pictureCode(slot))
    return
  }
  const picture = (event.target as HTMLElement).closest<HTMLImageElement>('.md-image--shown > img')
  if (picture) {
    openPicture(picture)
    return
  }
  const anchor = (event.target as HTMLElement).closest('a')
  if (anchor) {
    const href = anchor.getAttribute('href') ?? ''
    // Internal links (source citations et al.) navigate via the router — no full reload.
    // Modifier-click falls through to the browser so open-in-new-tab keeps working, and so does a
    // link that opens a tab of its own — a file, which no route of the app serves.
    const ownTab = anchor.getAttribute('target') === '_blank'
    if (href.startsWith('/') && !ownTab && !event.metaKey && !event.ctrlKey && !event.shiftKey) {
      event.preventDefault()
      router.push(href)
    }
    return
  }
  if (!props.allowImages) return
  const image = (event.target as HTMLElement).closest('img')
  if (image) emit('imageClick', (image as HTMLImageElement).currentSrc || image.getAttribute('src') || '')
}
</script>

<template>
  <div
    ref="body"
    v-bind="$attrs"
    class="md-body"
    :class="{ 'md-body--compact': compact }"
    @click="onClick"
    @contextmenu="onContextMenu"
    @mouseover="onPointerOver"
    @mouseout="onPointerOut"
    v-html="html"
  />
  <EntityPreviewPopup ref="popup" />
  <PictureMenu ref="pictureMenu" :code="menuCode" @open="openMenuPicture" />
  <ImageGallery v-model="lightbox" :codes="lightboxCodes" />
</template>

<!-- Body typography lives in the shared file and serves both zones — viewing and editing. The
     renderer no longer has a scoped block of its own: a second copy of these rules was exactly
     what drifted apart. -->
<style src="../shared/document.css"></style>
