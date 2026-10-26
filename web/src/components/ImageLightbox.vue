<script lang="ts">
/** One picture of a gallery: its address, its code when it is stored, what it is called and holds. */
export interface LightboxImage {
  src: string
  /** `IMAGE@…` — a stored picture: the panel reads it from its preview and copies the code. */
  code?: string
  title?: string
  description?: string
}
</script>

<script setup lang="ts">
/**
 * Full-screen preview of an image, opened by clicking an image in a body.
 * Driven by a v-model holding the image src — a non-empty src opens the dialog, closing
 * it clears the src. Clicking the backdrop, the image, or pressing Esc dismisses it.
 *
 * `images` is the gallery the image belongs to: with more than one, the arrows on screen, ←/→ and
 * A/D page through it, round at the ends, by rewriting the same v-model. The arrows stand at the
 * stage's edges, level with the middle of the picture's room, the keys written faintly under each —
 * in one place on the screen whatever is shown. Under the picture, centred, goes the media panel
 * (`files/MediaPanel.vue` — title and description, editable where the page allows, and download,
 * open and copy-code), as wide as what it says.
 *
 * On a phone (`mobile`) the viewer takes the whole screen; the arrows are small and sit in the
 * bottom corners, under the panel, where they cover neither the picture nor its text. There are no
 * keys to write, and a swipe across the picture pages too; a tap still closes.
 */
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { useDisplay } from 'vuetify'
import { IconChevronLeft, IconChevronRight } from '@tabler/icons-vue'

import MediaPanel from '@/components/files/MediaPanel.vue'

const props = defineProps<{ modelValue: string | null; images?: LightboxImage[] }>()
const emit = defineEmits<{ 'update:modelValue': [value: string | null] }>()

const { t } = useI18n()
const { mobile } = useDisplay()

// How tall the panel stands now — its description grows as it is typed: the picture gives it that
// room (`--caption-height`), so the two never leave the stage.
const caption = ref<HTMLElement | null>(null)
const captionHeight = ref<number | null>(null)

watch(caption, (element, _previous, onCleanup) => {
  if (!element) return
  const observer = new ResizeObserver(([entry]) => {
    captionHeight.value = Math.ceil(entry.borderBoxSize?.[0]?.blockSize ?? entry.target.getBoundingClientRect().height)
  })
  observer.observe(element)
  onCleanup(() => observer.disconnect())
})

const stageStyle = computed(() =>
  captionHeight.value === null ? undefined : { '--caption-height': `${captionHeight.value}px` },
)

const open = computed({
  get: () => !!props.modelValue,
  set: (value) => {
    if (!value) emit('update:modelValue', null)
  },
})

const gallery = computed(() => props.images ?? [])
const position = computed(() => gallery.value.findIndex((one) => one.src === props.modelValue))
const current = computed(() => gallery.value[position.value])
const pages = computed(() => gallery.value.length > 1 && position.value >= 0)

function page(step: -1 | 1): void {
  if (!pages.value) return
  const total = gallery.value.length
  emit('update:modelValue', gallery.value[(position.value + step + total) % total]?.src ?? null)
}

// On the window rather than on the dialog: focus may sit on the scrim, the stage or a button, and
// the keys must page from any of them. Esc stays the dialog's own. A and D are read by their place
// on the keyboard (`code`), so they page under any layout; with a modifier they are someone else's,
// and in a field of the panel they are typed.
function onKey(event: KeyboardEvent): void {
  if (event.ctrlKey || event.metaKey || event.altKey) return
  if (event.target instanceof HTMLInputElement || event.target instanceof HTMLTextAreaElement) return
  if (event.key === 'ArrowLeft' || event.code === 'KeyA') page(-1)
  else if (event.key === 'ArrowRight' || event.code === 'KeyD') page(1)
  else return
  event.preventDefault()
}

watch(open, (shown) => {
  if (shown) window.addEventListener('keydown', onKey)
  else window.removeEventListener('keydown', onKey)
}, { immediate: true })

// A swipe pages: a touch that went mostly sideways, far enough to be meant. The click the touch ends
// in is the swipe's, not a tap to close.
const SWIPE_MIN = 48
let touchStart: { x: number; y: number } | null = null
let swiped = false

function onPointerDown(event: PointerEvent): void {
  touchStart = event.pointerType === 'touch' ? { x: event.clientX, y: event.clientY } : null
}

function onPointerUp(event: PointerEvent): void {
  if (!touchStart) return
  const dx = event.clientX - touchStart.x
  const dy = event.clientY - touchStart.y
  touchStart = null
  if (Math.abs(dx) < SWIPE_MIN || Math.abs(dx) < Math.abs(dy) * 1.5) return
  swiped = true
  page(dx < 0 ? 1 : -1)
}

function onStageClick(): void {
  if (swiped) {
    swiped = false
    return
  }
  open.value = false
}

onBeforeUnmount(() => window.removeEventListener('keydown', onKey))
</script>

<template>
  <VDialog
    v-model="open"
    :max-width="mobile ? undefined : '92vw'"
    :fullscreen="mobile"
    :scrim="true"
    class="image-lightbox"
  >
    <figure
      class="image-lightbox__stage"
      :class="{ 'image-lightbox__stage--mobile': mobile }"
      :style="stageStyle"
      @click="onStageClick"
      @pointerdown="onPointerDown"
      @pointerup="onPointerUp"
    >
      <div class="image-lightbox__view">
        <div class="image-lightbox__frame">
          <img :src="modelValue ?? ''" :alt="current?.title ?? ''" class="image-lightbox__img" />
          <div v-if="pages" class="image-lightbox__counter">
            {{ t('common.lightbox.position', { index: position + 1, total: gallery.length }) }}
          </div>
        </div>
      </div>
      <div ref="caption" class="image-lightbox__caption">
        <MediaPanel
          v-if="modelValue"
          :src="modelValue"
          :code="current?.code"
          :title="current?.title"
          :description="current?.description"
        />
      </div>
      <template v-if="pages">
        <div class="image-lightbox__side image-lightbox__side--prev">
          <VBtn
            icon
            variant="flat"
            :size="mobile ? 'small' : 'default'"
            class="image-lightbox__nav"
            :aria-label="t('common.lightbox.previous')"
            :title="t('common.lightbox.previous')"
            aria-keyshortcuts="ArrowLeft A"
            @click.stop="page(-1)"
          >
            <IconChevronLeft :size="mobile ? 20 : 24" />
          </VBtn>
          <div v-if="!mobile" class="image-lightbox__keys" aria-hidden="true"><kbd>←</kbd><kbd>A</kbd></div>
        </div>
        <div class="image-lightbox__side image-lightbox__side--next">
          <VBtn
            icon
            variant="flat"
            :size="mobile ? 'small' : 'default'"
            class="image-lightbox__nav"
            :aria-label="t('common.lightbox.next')"
            :title="t('common.lightbox.next')"
            aria-keyshortcuts="ArrowRight D"
            @click.stop="page(1)"
          >
            <IconChevronRight :size="mobile ? 20 : 24" />
          </VBtn>
          <div v-if="!mobile" class="image-lightbox__keys" aria-hidden="true"><kbd>→</kbd><kbd>D</kbd></div>
        </div>
      </template>
    </figure>
  </VDialog>
</template>

<style scoped>
/* The stage is one size whatever it shows — nearly the whole screen, short of the dialog's own
   margins — so the arrows at its edges stand still: sized by the picture or its caption, the stage
   moved them from one page of a gallery to the next. The picture and its panel right under it are
   centred in it together. */
.image-lightbox__stage {
  --stage-width: min(92vw, calc(100vw - 48px));
  --stage-height: min(92vh, calc(100vh - 48px));
  /* The panel's room: its height as measured now, and the gap above it — the picture never takes
     it. Before the first measure, a panel of one title line. */
  --caption-room: calc(var(--caption-height, 46px) + 10px);
  /* Where the arrows stand: the middle of the picture's room under a panel of usual height. A
     constant, so a growing description never moves them. */
  --arrow-level: calc((var(--stage-height) - 136px) / 2);
  position: relative;
  display: flex;
  flex-direction: column;
  justify-content: center;
  width: var(--stage-width);
  height: var(--stage-height);
  margin: 0;
  cursor: zoom-out;
}

.image-lightbox__view {
  display: flex;
  flex: none;
  justify-content: center;
}

/* The panel centred under the picture, no wider than the text measure a caption reads at. */
.image-lightbox__caption {
  --media-panel-max-width: min(720px, var(--stage-width));
  display: flex;
  flex: none;
  justify-content: center;
  margin-top: 10px;
}

/* On a phone the viewer is the whole screen, short of a margin and the notches. The picture keeps a
   room of its own on top, the panel goes under it and may take its whole width, and the arrows'
   corners stay free at the bottom. */
.image-lightbox__stage--mobile {
  --stage-width: calc(100vw - 16px);
  --stage-height: calc(100dvh - 16px - env(safe-area-inset-top) - env(safe-area-inset-bottom));
  /* The panel as measured, the arrows' corners under it and the gaps. */
  --caption-room: calc(var(--caption-height, 46px) + 10px + 44px);
  justify-content: flex-start;
  margin: calc(8px + env(safe-area-inset-top)) 8px calc(8px + env(safe-area-inset-bottom));
}

.image-lightbox__stage--mobile .image-lightbox__view {
  align-items: center;
  height: calc(var(--stage-height) - var(--caption-room));
}

.image-lightbox__stage--mobile .image-lightbox__caption {
  --media-panel-max-width: var(--stage-width);
}

/* The frame alone rounds the picture. Its white backing stops a pixel short of the edge: drawn up to
   it, the backing was cut along the arc as well as the picture, each with its own smoothing, and
   the white showed through in the corners' pixels. */
.image-lightbox__frame {
  position: relative;
  display: flex;
  overflow: hidden;
  border-radius: 8px;
  box-shadow: 0 12px 48px rgba(0, 0, 0, 0.45);
}

/* Transparent PNGs would otherwise blend into the dark scrim — back them with white. */
.image-lightbox__frame::before {
  content: '';
  position: absolute;
  inset: 1px;
  border-radius: 7px;
  background: #fff;
}

.image-lightbox__img {
  /* Above the backing, which is positioned. */
  position: relative;
  display: block;
  max-width: var(--stage-width);
  max-height: calc(var(--stage-height) - var(--caption-room));
  object-fit: contain;
}

/* An arrow with its keys written under it, at the stage's edge, at one level: one place on the
   screen whatever is shown. */
.image-lightbox__side {
  position: absolute;
  top: var(--arrow-level);
  transform: translateY(-50%);
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 8px;
}

.image-lightbox__side--prev { left: 12px; }
.image-lightbox__side--next { right: 12px; }

/* On a phone: small, in the bottom corners, under the panel. */
.image-lightbox__stage--mobile .image-lightbox__side {
  top: auto;
  bottom: 0;
  transform: none;
}

.image-lightbox__stage--mobile .image-lightbox__side--prev { left: 0; }
.image-lightbox__stage--mobile .image-lightbox__side--next { right: 0; }

.image-lightbox__nav {
  background: rgba(0, 0, 0, 0.55);
  color: #fff;
}

/* A hint, not a control: faint, and the pointer passes through to the stage. A screen with no
   pointer to hover with has no keyboard to name either. */
.image-lightbox__keys {
  display: flex;
  gap: 4px;
  opacity: 0.55;
  pointer-events: none;
}

@media (hover: none) {
  .image-lightbox__keys { display: none; }
}

.image-lightbox__keys kbd {
  min-width: 18px;
  padding: 2px 5px;
  border: 1px solid rgba(255, 255, 255, 0.28);
  border-radius: 3px;
  background: rgba(0, 0, 0, 0.35);
  color: #fff;
  font-family: var(--font-mono);
  font-size: 11px;
  line-height: 1;
  text-align: center;
}

.image-lightbox__counter {
  position: absolute;
  bottom: 12px;
  left: 50%;
  transform: translateX(-50%);
  padding: 2px 10px;
  border-radius: 12px;
  font-size: 13px;
  color: #fff;
  background: rgba(0, 0, 0, 0.55);
  pointer-events: none;
}
</style>

<!-- The scrim is teleported outside this component, so it can't be reached from scoped
     styles; the dialog's `image-lightbox` class falls through to the overlay root. -->
<style>
.image-lightbox.v-overlay .v-overlay__scrim {
  background: #000;
  opacity: 0.75;
}
</style>
