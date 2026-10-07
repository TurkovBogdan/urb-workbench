<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import {
  IconArrowsMinimize,
  IconMaximize,
  IconX,
  IconZoomIn,
  IconZoomOut,
  IconZoomReset,
} from '@tabler/icons-vue'

import type { DiagramColors } from 'beautiful-mermaid'

import { NO_DIAGRAM_HEIGHT, diagramAlign } from '@/constants/diagrams'
import { DEFAULT_DIAGRAM_FONT, DIAGRAM_FONTS, fontFamilyName } from '@/constants/fonts'
import { useSettingsStore } from '@/stores/settings'
import CodeBlock from './CodeBlock.vue'

// A diagram from a document body: mermaid source → SVG. In the body it sits as a preview fitted
// to the column width; it is examined in fullscreen — with zoom and pan, like on a whiteboard.
// Anything that fails to render (unknown type, syntax beyond the parser) falls back to a code
// block: the reader still sees the source, and the body doesn't break.
const props = defineProps<{ code: string }>()

const { t } = useI18n()

// The render engine is 1.6 MB (almost all of it the ELK layout), so it arrives as a separate
// chunk on the first diagram of a page rather than in the main bundle. The promise is app-wide.
let engine: Promise<typeof import('beautiful-mermaid')> | null = null

function loadEngine() {
  engine ??= import('beautiful-mermaid')
  return engine
}

// The diagram type comes from the first non-empty source line, not the fence tag (always `mermaid`).
// The value is the header label; a missing key means "the renderer can't do this type".
const DIAGRAM_LABEL: Record<string, string> = {
  graph: 'flowchart',
  flowchart: 'flowchart',
  stateDiagram: 'state',
  'stateDiagram-v2': 'state',
  sequenceDiagram: 'sequence',
  classDiagram: 'class',
  erDiagram: 'ER',
  'xychart-beta': 'chart',
}

const label = computed(() => {
  const header = props.code.split('\n').find((line) => line.trim().length)
  return DIAGRAM_LABEL[header?.trim().split(/\s+/)[0] ?? ''] ?? ''
})

// Colors go into the SVG as references to theme tokens, not their values: the library puts each
// into a CSS variable on the <svg> itself and derives the rest of the palette via color-mix().
// Switching the dark/light theme rewrites the tokens on <html> and reaches here through the
// cascade — no redraw and no re-layout. The full set is specified: the library's variable names
// match the app's token names, and an unset one would reach the diagram from the general
// cascade — by accident, not by decision.
const THEME_COLORS = {
  bg: 'var(--surface)',
  fg: 'var(--text)',
  muted: 'var(--text-muted)',
  line: 'var(--text-faint)',
  accent: 'var(--accent)',
  surface: 'var(--surface-hi)',
  border: 'var(--border)',
}

// A built-in engine palette sets only some roles and derives the rest from `bg`+`fg` as a fallback
// inside `var(--surface, …)`. The app's tokens have exactly the same names and are declared on the
// document root — the fallback never reaches the diagram, the app color is substituted instead,
// and on a dark palette the boxes come out white. So all roles are filled in; the shares are the
// same ones the engine uses in its own derivations.
const PALETTE_BLEND = { line: 50, accent: 85, muted: 40, surface: 3, border: 20 }

function wholePalette(palette: DiagramColors): DiagramColors {
  const blend = (share: number) => `color-mix(in srgb, ${palette.fg} ${share}%, ${palette.bg})`
  return {
    bg: palette.bg,
    fg: palette.fg,
    line: palette.line ?? blend(PALETTE_BLEND.line),
    accent: palette.accent ?? blend(PALETTE_BLEND.accent),
    muted: palette.muted ?? blend(PALETTE_BLEND.muted),
    surface: palette.surface ?? blend(PALETTE_BLEND.surface),
    border: palette.border ?? blend(PALETTE_BLEND.border),
  }
}

// The renderer writes a Google Fonts @import into the diagram's <style>. The app is local and has
// its own typefaces (styles/fonts.scss) — the outbound request is neither needed nor would it get
// through when working offline.
const FONT_IMPORT = /^\s*@import url\('https:\/\/fonts\.googleapis\.com[^\n]*\n/gm

// Typefaces are loaded as subsets with `font-display: swap` and fetched only when needed — that is,
// at the first diagram. By then the layout is already computed, so swapping the font on the fly
// shifts the labels in plain view. Wait for the needed faces before inserting the SVG.
// The sample string must carry both Cyrillic and Latin: a subset is fetched for specific text.
const FONT_SAMPLE = 'Схема Diagram 123'

async function loadFontFaces(family: string): Promise<void> {
  if (!document.fonts) return
  const faces = [`400 13px "${family}"`, `600 13px "${family}"`, '400 13px "JetBrains Mono"']
  await Promise.all(faces.map((face) => document.fonts.load(face, FONT_SAMPLE))).catch(() => undefined)
}

const settings = useSettingsStore()

const family = computed(() =>
  fontFamilyName(DIAGRAM_FONTS, settings.diagrams.font, DEFAULT_DIAGRAM_FONT),
)

// Block styling goes to CSS as variables: alignment via auto margins (the block is as wide as its
// content, so that is how centering is done), the height cap as `none` when it has been lifted.
const frame = computed(() => ({
  '--diagram-side-margin': diagramAlign(settings.diagrams.align) === 'center' ? 'auto' : '0',
  '--diagram-max-height':
    settings.diagrams.maxHeight === NO_DIAGRAM_HEIGHT ? 'none' : `${settings.diagrams.maxHeight}px`,
}))

const svg = ref('')
const unsupported = ref(false)

async function draw() {
  if (!label.value) {
    unsupported.value = true
    return
  }
  try {
    const [{ renderMermaidSVG, THEMES }] = await Promise.all([loadEngine(), loadFontFaces(family.value)])
    // A built-in palette brings its own background, so transparency is turned off along with it:
    // otherwise the diagram would sit on the card background and half the palette would vanish.
    // An unknown code (the palette disappeared from the engine) means system colors, not an empty diagram.
    const palette = THEMES[settings.diagrams.theme]
    svg.value = renderMermaidSVG(props.code, {
      ...(palette ? wholePalette(palette) : THEME_COLORS),
      font: family.value,
      transparent: palette === undefined,
      padding: 8,
    }).replace(FONT_IMPORT, '')
  } catch {
    svg.value = ''
    unsupported.value = true
  }
}

onMounted(draw)
// The typeface and palette are baked into the diagram markup, so changing them means a redraw.
// One exception: the system palette goes into the SVG as references to app tokens, and a
// dark/light theme switch reaches it through the cascade, without re-layout.
watch([() => props.code, family, () => settings.diagrams.theme], draw)

// ── Fullscreen mode: zoom toward the pointer, pan by dragging ─────────────────
const ZOOM_LIMITS = { min: 0.2, max: 8 }
const ZOOM_STEP = 1.15
// Share of the frame a fitted diagram occupies: breathing room at the edges keeps the outermost
// boxes from running into the control panel and the screen edge.
const FIT_MARGIN = 0.92

const fullscreen = ref(false)
const stage = ref<HTMLElement | null>(null)
const view = reactive({ scale: 1, x: 0, y: 0 })
const panning = ref(false)
const spaceHeld = ref(false)

const zoomPercent = computed(() => Math.round(view.scale * 100))

const transform = computed(() => `translate(${view.x}px, ${view.y}px) scale(${view.scale})`)

function diagramSize(): { width: number; height: number } | null {
  const rendered = stage.value?.querySelector('svg')
  if (!rendered) return null
  return { width: Number(rendered.getAttribute('width')), height: Number(rendered.getAttribute('height')) }
}

function fit() {
  const size = diagramSize()
  const frame = stage.value
  if (!size || !frame || !size.width || !size.height) return
  const scale = clamp(Math.min(frame.clientWidth / size.width, frame.clientHeight / size.height) * FIT_MARGIN)
  applyScale(scale, (frame.clientWidth - size.width * scale) / 2, (frame.clientHeight - size.height * scale) / 2)
}

function actualSize() {
  const size = diagramSize()
  const frame = stage.value
  if (!size || !frame) return
  applyScale(1, (frame.clientWidth - size.width) / 2, (frame.clientHeight - size.height) / 2)
}

function applyScale(scale: number, x: number, y: number) {
  view.scale = scale
  view.x = x
  view.y = y
}

function clamp(scale: number): number {
  return Math.min(ZOOM_LIMITS.max, Math.max(ZOOM_LIMITS.min, scale))
}

// Zoom keeps the point under the pointer in place — otherwise at 5x the node of interest slides
// out of frame on the very first wheel click.
function zoomAt(clientX: number, clientY: number, factor: number) {
  const frame = stage.value?.getBoundingClientRect()
  if (!frame) return
  const pointerX = clientX - frame.left
  const pointerY = clientY - frame.top
  const scale = clamp(view.scale * factor)
  const ratio = scale / view.scale
  applyScale(scale, pointerX - ratio * (pointerX - view.x), pointerY - ratio * (pointerY - view.y))
}

function zoomCenter(factor: number) {
  const frame = stage.value
  if (!frame) return
  const box = frame.getBoundingClientRect()
  zoomAt(box.left + frame.clientWidth / 2, box.top + frame.clientHeight / 2, factor)
}

function onWheel(event: WheelEvent) {
  zoomAt(event.clientX, event.clientY, event.deltaY < 0 ? ZOOM_STEP : 1 / ZOOM_STEP)
}

// Dragging pans only while Space is held — otherwise text couldn't be selected in the diagram,
// and it is real text: this is SVG, not an image. Selection is suppressed while panning: without
// `preventDefault` the browser starts extending a selection on the same press, and the diagram
// moves along with highlighted text.
function onPointerDown(event: PointerEvent) {
  if (!spaceHeld.value) return
  event.preventDefault()
  document.getSelection()?.removeAllRanges()
  panning.value = true
  ;(event.currentTarget as HTMLElement).setPointerCapture(event.pointerId)
}

function onPointerMove(event: PointerEvent) {
  if (!panning.value) return
  view.x += event.movementX
  view.y += event.movementY
}

function onPointerUp(event: PointerEvent) {
  if (!panning.value) return
  panning.value = false
  ;(event.currentTarget as HTMLElement).releasePointerCapture(event.pointerId)
}

function onKeyDown(event: KeyboardEvent) {
  if (!fullscreen.value) return
  if (event.code === 'Space') {
    spaceHeld.value = true
    event.preventDefault()
    return
  }
  const shortcut: Record<string, () => void> = {
    '0': fit,
    '1': actualSize,
    '+': () => zoomCenter(ZOOM_STEP),
    '=': () => zoomCenter(ZOOM_STEP),
    '-': () => zoomCenter(1 / ZOOM_STEP),
  }
  shortcut[event.key]?.()
}

function onKeyUp(event: KeyboardEvent) {
  if (event.code !== 'Space') return
  spaceHeld.value = false
  panning.value = false
}

async function open() {
  if (!svg.value) return
  fullscreen.value = true
  await nextTick()
  fit()
}

watch(fullscreen, (isOpen) => {
  if (isOpen) return
  spaceHeld.value = false
  panning.value = false
})

onMounted(() => {
  window.addEventListener('keydown', onKeyDown)
  window.addEventListener('keyup', onKeyUp)
})

onBeforeUnmount(() => {
  window.removeEventListener('keydown', onKeyDown)
  window.removeEventListener('keyup', onKeyUp)
})
</script>

<template>
  <CodeBlock v-if="unsupported" :code="code" lang="mermaid" variant="icon" />

  <div v-else-if="!svg" class="diagram-loading">
    <VProgressCircular indeterminate size="16" width="2" />
    {{ t('common.diagram.loading') }}
  </div>

  <figure v-else class="diagram" :style="frame" @dblclick="open">
    <div class="diagram__preview" v-html="svg" />
    <figcaption class="diagram__hint">
      <IconMaximize :size="13" stroke-width="2" />
      {{ t('common.diagram.open_hint') }}
    </figcaption>
  </figure>

  <VDialog v-model="fullscreen" fullscreen :scrim="false" transition="fade-transition">
    <div class="viewer">
      <div
        ref="stage"
        class="viewer__stage"
        :class="{ 'viewer__stage--grab': spaceHeld, 'viewer__stage--grabbing': panning }"
        @wheel.prevent="onWheel"
        @pointerdown="onPointerDown"
        @pointermove="onPointerMove"
        @pointerup="onPointerUp"
        @pointercancel="onPointerUp"
        @dblclick="fit"
      >
        <div class="viewer__canvas" :style="{ transform }" v-html="svg" />
      </div>

      <button class="viewer__btn viewer__close" :title="t('common.diagram.close')" @click="fullscreen = false">
        <IconX :size="18" stroke-width="2" />
      </button>

      <div class="viewer__controls">
        <button class="viewer__btn" :title="t('common.diagram.zoom_out')" @click="zoomCenter(1 / ZOOM_STEP)">
          <IconZoomOut :size="17" stroke-width="1.8" />
        </button>
        <span class="viewer__percent">{{ zoomPercent }}%</span>
        <button class="viewer__btn" :title="t('common.diagram.zoom_in')" @click="zoomCenter(ZOOM_STEP)">
          <IconZoomIn :size="17" stroke-width="1.8" />
        </button>
        <span class="viewer__divider" />
        <button class="viewer__btn" :title="t('common.diagram.fit')" @click="fit">
          <IconArrowsMinimize :size="17" stroke-width="1.8" />
        </button>
        <button class="viewer__btn" :title="t('common.diagram.actual_size')" @click="actualSize">
          <IconZoomReset :size="17" stroke-width="1.8" />
        </button>
      </div>

      <p class="viewer__legend">{{ t('common.diagram.legend') }}</p>
    </div>
  </VDialog>
</template>

<style scoped>
/* Space for the diagram is reserved up front: the engine's first chunk weighs a megabyte and a
   half, and without a reservation the document would jump when it arrives. The block itself is
   empty — a border and fill would draw an object that doesn't exist yet; only a line saying what
   is happening remains. */
.diagram-loading {
  display: flex;
  align-items: center;
  gap: 8px;
  height: 220px;
  margin: 16px 0;
  font-family: var(--font-mono);
  font-size: 11px;
  color: var(--text-faint);
}

/* The spinner is grey, not accent: a diagram loading is not an event worth signalling with color.
   The stroke is painted directly, so the accent `color` every spinner gets from main.scss and the
   theme defaults does not matter here. */
.diagram-loading :deep(.v-progress-circular__overlay) {
  stroke: var(--text-faint);
}

/* Width fits the content: the hover border outlines the diagram, not an empty strip up to the
   right edge. The cap is the full available width; beyond it the diagram shrinks. */
.diagram {
  width: fit-content;
  max-width: 100%;
  margin: 16px var(--diagram-side-margin, 0);
  padding: 12px;
  border: 1px solid transparent;
  border-radius: var(--radius);
  transition: border-color .15s, background .15s;
}

.diagram:hover {
  border-color: var(--border);
  background: var(--surface);
}

/* The diagram is left-aligned, not centered: the surrounding text is bound to the reading column,
   and a narrow diagram centered across the full width breaks away from that column — the document
   stops reading top to bottom along one vertical. */
.diagram__preview {
  display: flex;
  justify-content: flex-start;
}

/* The preview is always fitted: the diagram is examined in fullscreen, not here, so there is no
   horizontal scrolling in the document body. The height cap is a setting: otherwise a long
   diagram crowds out the text the document was opened for. */
.diagram__preview :deep(svg) {
  max-width: 100%;
  max-height: var(--diagram-max-height, 420px);
  width: auto;
  height: auto;
}

/* The caption says not what this is but what to do with it: the reader sees the diagram type
   from the diagram itself, but has no way to guess about fullscreen. */
.diagram__hint {
  display: flex;
  align-items: center;
  gap: 5px;
  margin-top: 8px;
  font-family: var(--font-mono);
  font-size: 11px;
  color: var(--text-faint);
}

.viewer {
  position: relative;
  width: 100vw;
  /* dvh, not vh: on mobile 100vh is taller than the screen while the address bar shows, and the
     bottom of the viewer — its controls included — would sit under it. */
  height: 100dvh;
  background: var(--bg);
}

.viewer__stage {
  width: 100%;
  height: 100%;
  overflow: hidden;
  touch-action: none;
  cursor: default;
}

/* While Space is held the canvas is a move tool, not text: selection is disabled entirely,
   otherwise, even suppressed on press, it comes back on a habitual double-click or Ctrl+A. */
.viewer__stage--grab {
  cursor: grab;
  user-select: none;
}

.viewer__stage--grabbing { cursor: grabbing; }

/* The origin is at the top-left corner: the zoom-to-pointer math assumes scale grows from this
   point, not from the frame center.

   `will-change: transform` was harmful here: the layer moves to the compositor, is rasterized once
   at the original scale and then stretched as a bitmap — the vector diagram turned blurry.
   Without it the browser redraws the SVG on every zoom step and the lines stay sharp. */
.viewer__canvas {
  transform-origin: 0 0;
}

/* The reset is required: the panel is teleported to an overlay outside the app, where the browser
   draws a grey plate with a border on a `<button>` — the project has no global reset. */
.viewer__btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  height: 32px;
  min-width: 32px;
  appearance: none;
  border: 0;
  border-radius: var(--radius-sm);
  background: transparent;
  color: #5b6472;
  cursor: pointer;
  transition: color .12s, background .12s;
}

.viewer__btn:hover {
  color: #16191f;
  background: rgb(0 0 0 / 6%);
}

.viewer__percent {
  min-width: 48px;
  text-align: center;
  font-family: var(--font-mono);
  font-size: 12px;
  color: #5b6472;
  user-select: none;
}

.viewer__divider {
  width: 1px;
  height: 20px;
  margin: 0 4px;
  background: rgb(0 0 0 / 12%);
}

/* The controls are always light, in both themes: the canvas beneath is sometimes dark, sometimes
   white, and a panel that followed the theme would drown on half the diagrams. Hence its own
   colors instead of tokens — this is not an app UI element but a tool over an image. These rules
   come after the button ones: they draw the plate, not the reset inside. */
.viewer__close,
.viewer__controls {
  position: absolute;
  border: 1px solid rgb(0 0 0 / 12%);
  border-radius: var(--radius);
  background: #fff;
}

.viewer__close {
  top: 16px;
  right: 16px;
  width: 34px;
  height: 34px;
}

/* The zoom panel sits at the center of the bottom edge — the eyes work around the frame center,
   and the top-right corner is taken by the close button. */
.viewer__controls {
  left: 50%;
  bottom: 20px;
  transform: translateX(-50%);
  display: flex;
  align-items: center;
  gap: 2px;
  padding: 4px;
}

.viewer__legend {
  position: absolute;
  left: 16px;
  bottom: 24px;
  margin: 0;
  font-size: 11px;
  color: var(--text-faint);
  user-select: none;
}
</style>
