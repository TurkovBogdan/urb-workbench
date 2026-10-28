<script setup lang="ts">
// A document laid out as a sheet of paper — the page a print address shows. A hidden frame opens
// that address (`printPage`) and sends it to the virtual printer, so what is drawn here is what
// lands in the PDF; opened directly, the address shows exactly the same on screen.
//
// The body goes through the same `MarkdownRenderer` as on the document's own page — pictures,
// galleries, diagrams, code, tables and pills are drawn by the code that draws them everywhere —
// and only the sheet's look is its own: it reads as a document, not as a page of the app. No
// buttons, hints or tinted pills, type set in points, margins and page numbers from `@page`.
import { nextTick, onActivated, onBeforeUnmount, onDeactivated, ref, watch } from 'vue'

import MarkdownRenderer from '@/components/markdown/renderer/MarkdownRenderer.vue'
import { usePreviews } from '@/stores/preview'
import { useSettingsStore } from '@/stores/settings'
import { announcePrintFailure, announcePrintReady } from '@/shared/utils/print'

export interface PrintedDocument {
  title: string
  /** Markdown, set under the title as the lead; empty — no lead. */
  description: string
  /** The line under the lead — code, path, date — joined with a middle dot. */
  meta: string[]
  /** Markdown. */
  body: string
}

const props = defineProps<{
  document: PrintedDocument | null
  /** The failure that left nothing to print; it goes to the frame instead of a document. */
  error: string
}>()

const settings = useSettingsStore()
const previews = usePreviews()

// The sheet is white paper whatever the person's theme: background fills are not printed by
// default, and under the dark theme light text would land on white. Paired with the page's
// presence, so a sheet opened in the app's own tab gives the theme back on leaving.
onActivated(() => settings.setPaper(true))
onDeactivated(() => settings.setPaper(false))
onBeforeUnmount(() => settings.setPaper(false))

const sheet = ref<HTMLElement | null>(null)

// Printing cannot go on the page's load event: by then the document has not arrived, the body is
// not parsed, the code not highlighted, the diagrams not drawn and the pictures not loaded — half
// an empty document would land on the sheet. Each of those leaves a mark in the body until it is
// done, and the sheet waits for all of them to go.
const DRAWN_POLL_MS = 100
const DRAWN_TIMEOUT_MS = 20_000

function pending(root: HTMLElement): boolean {
  // A slot the renderer has not mounted its block into yet, a listing not yet highlighted.
  if (root.querySelector('.md-code-slot:empty, .diagram-loading')) return true
  if ([...root.querySelectorAll('.code-block__body')].some((listing) => !listing.childElementCount)) return true
  // A pill whose preview has not come: it would print without its address, a picture without its file.
  if ([...root.querySelectorAll<HTMLElement>('.md-ref[data-ref]')].some((pill) => !previews.get(pill.dataset.ref ?? ''))) return true
  if (root.querySelector('.md-image--pending')) return true
  return [...root.querySelectorAll<HTMLImageElement>('.md-image > img')].some((image) => !image.complete)
}

// What is not done within the time does not cancel the print: a diagram that would not draw falls
// back to its source, a picture that would not load to its pill, and a sheet with those beats a
// print that never happens.
async function whenDrawn(): Promise<void> {
  await nextTick()
  await globalThis.document.fonts?.ready
  const deadline = Date.now() + DRAWN_TIMEOUT_MS
  const settle = () => new Promise((wake) => setTimeout(wake, DRAWN_POLL_MS))
  while (sheet.value && pending(sheet.value) && Date.now() < deadline) await settle()
  // A loaded picture lays its gallery out again with its own proportions — a pass after the last
  // mark is gone lets that land before the sheet is taken.
  await settle()
  await globalThis.document.fonts?.ready
}

// The frame waits for one answer per document. A sheet opened in the app's own tab may be emptied
// for the next document, and that one is answered afresh.
let announced = false

watch(
  () => [props.document, props.error] as const,
  async ([printed, error]) => {
    if (!printed && !error) {
      announced = false
      return
    }
    if (announced) return
    if (error) {
      announced = true
      announcePrintFailure(error)
      return
    }
    if (!printed) return
    announced = true
    // The browser names the saved file after the document's title: without it every PDF would be
    // called by the route's generic caption.
    globalThis.document.title = printed.title
    await whenDrawn()
    announcePrintReady()
  },
  { immediate: true },
)
</script>

<template>
  <div class="print-page">
    <article v-if="document" ref="sheet" class="print-doc">
      <header class="print-doc__head">
        <h1 class="print-doc__title">{{ document.title }}</h1>
        <MarkdownRenderer v-if="document.description" :text="document.description" class="print-doc__lead" />
        <p v-if="document.meta.length" class="print-doc__meta">{{ document.meta.join(' · ') }}</p>
      </header>

      <MarkdownRenderer v-if="document.body" :text="document.body" class="print-doc__body" />
    </article>

    <p v-else-if="error" class="print-doc__error">{{ error }}</p>
  </div>
</template>

<style scoped>
/* On screen the page scrolls by itself: it stands outside the app's page frame, which is what
   usually gives a page its scrolling zone. */
.print-page {
  height: 100%;
  overflow: auto;
  background: #fff;
  /* Fills are part of the document here — a listing's tint, a table's header row — and the browser
     drops them from print unless told otherwise. */
  print-color-adjust: exact;
  -webkit-print-color-adjust: exact;
}

/* The width of an A4 sheet without its margins, on screen as well: what is printed should be seen
   the way it goes to the printer, not at the window's width. */
.print-doc {
  /* The sheet's scale is its own, not the person's reading setup: paper is read at arm's length in
     points, and a light weight chosen for a screen prints as hairlines. The measure goes too — on a
     sheet the column is the page itself. */
  --reading-size: 10.5pt;
  --reading-weight: 400;
  --reading-measure: 100%;
  /* The sheet's useful height: A4 minus the margins (`@page`) and minus room for more than one
     diagram on a page. A diagram is not let past it: paper does not scroll, a bottom that ran off
     would be lost. */
  --sheet-height: 230mm;

  max-width: 178mm;
  margin: 0 auto;
  padding: 18mm 0 24mm;
  color: #1a1a1a;
  page: print-sheet;
}

/* On paper the margins are the page's own (`@page`). */
@media print {
  .print-doc {
    max-width: none;
    padding: 0;
  }
}

.print-doc__head {
  margin-bottom: 18pt;
  padding-bottom: 10pt;
  border-bottom: 0.75pt solid #c8c8c8;
}

.print-doc__title {
  font-family: var(--font-heading, var(--font-reading));
  font-size: 20pt;
  font-weight: 700;
  line-height: 1.2;
  letter-spacing: -0.01em;
  margin: 0 0 8pt;
  color: #111;
  text-wrap: balance;
}

.print-doc__meta,
.print-doc__error {
  font-family: var(--font);
  font-size: 8.5pt;
  line-height: 1.4;
  color: #6b6b6b;
  margin: 8pt 0 0;
}

.print-doc__error {
  margin: 0;
  padding: 24px;
}

/* ── The body as a document ───────────────────────────────── */

.print-doc :deep(.md-body) {
  line-height: 1.55;
  color: #1a1a1a;
}

/* The renderer's root is a fragment, so the class it is given lands past this component's scope. */
.print-doc :deep(.print-doc__lead) {
  --reading-size: 11pt;
  line-height: 1.5;
  color: #4a4a4a;
}

/* A pill is an identifier in running text, not a plate: the code alone, in the monospace of code,
   linked where it leads somewhere. The glyph, the tint and the frame are the screen's way of
   telling types apart under a pointer, and paper has no pointer. */
.print-doc :deep(.md-body .md-ref) {
  padding: 0;
  margin: 0;
  border: 0;
  border-radius: 0;
  background: none;
  color: #1a1a1a;
  font-size: 0.86em;
}

.print-doc :deep(.md-body .md-ref::before) {
  display: none;
}

/* A code that leads nowhere still says so on paper: struck through and red, as the screen shows it. */
.print-doc :deep(.md-body .md-ref.md-ref--missing) {
  color: #b42318;
  text-decoration: line-through;
}

.print-doc :deep(.md-body a:not(.md-ref, .md-ref-label)) {
  color: #1d4ed8;
  text-decoration-color: color-mix(in srgb, #1d4ed8 45%, transparent);
}

/* Pictures without the controls laid over them. */
.print-doc :deep(.md-image__copy) {
  display: none;
}

/* A listing is a framed block of text: no header with its buttons, and long lines wrap — on paper
   there is no scrolling sideways, and what runs past the edge is gone. */
.print-doc :deep(.code-block__header),
.print-doc :deep(.code-block__copy-float) {
  display: none;
}

.print-doc :deep(.code-block__body),
.print-doc :deep(.code-block__body :is(pre, code)) {
  overflow: visible;
}

/* The document's `pre code` holds `white-space: pre` itself, so the listing is unwrapped on both. */
.print-doc :deep(.code-block__body :is(pre, code)) {
  white-space: pre-wrap;
  overflow-wrap: anywhere;
}

/* A wrapped line hangs: its continuation is indented past the start of the line — and past the
   line number, where they are shown — so it does not read as a line of its own. Each line is a
   full-width box for that; the newline after it still ends the row, so no blank rows appear. */
.print-doc :deep(.code-block__body .line) {
  display: inline-block;
  box-sizing: border-box;
  width: 100%;
  padding-left: 2em;
  text-indent: -2em;
}

.print-doc :deep(.code-block__body--line-numbers .line) {
  padding-left: 3.4em;
  text-indent: -3.4em;
}

/* A table takes the column's width and wraps its cells instead of scrolling in its frame. */
.print-doc :deep(.md-body .md-table-wrap) {
  overflow: visible;
}

.print-doc :deep(.md-body .md-table) {
  width: 100%;
  min-width: 0;
}

/* `break-word`, not `anywhere`: only a word longer than its column is broken, and the columns are
   still sized by whole words — `anywhere` let the table squeeze a column down to single letters. */
.print-doc :deep(.md-body .md-table :is(th, td)) {
  max-width: none;
  white-space: normal;
  overflow-wrap: break-word;
}

/* A diagram keeps its natural size, as a figure in a document does, and stands in the middle of the
   column. Only what does not fit is shrunk: wider than the column, or taller than the sheet — paper
   neither scrolls nor opens full screen, and what runs off it does not exist for the reader. The
   screen's height cap goes with the screen: on paper the sheet itself is the limit. The proportions
   are the diagram's own (`viewBox`), so it is fitted, not cut. The canvas behind it goes too: on
   paper the sheet is the canvas. */
.print-doc :deep(.diagram) {
  margin: 12pt 0;
  padding: 0;
  background: none;
  border: 0;
  box-shadow: none;
}

.print-doc :deep(.diagram__preview) {
  justify-content: center;
}

.print-doc :deep(.diagram__preview svg) {
  max-height: var(--sheet-height);
}

.print-doc :deep(.diagram__hint) {
  display: none;
}

/* A page break through a diagram, a picture, a table row or a listing makes both halves unreadable,
   and a heading at the foot of a page tears a section from its first line. */
.print-doc :deep(:is(figure, .md-image, .md-code-slot, tr, blockquote)) {
  break-inside: avoid;
}

/* The screen trims a heading's box to its cap height (`text-box`), and what rises above it — an
   ascender, the bar of a capital — is ink outside the box. A heading moved to the next page left
   that ink behind at the foot of the previous one, a sliver of letters under the last line. */
.print-doc :deep(:is(h1, h2, h3, h4, h5, h6)) {
  break-after: avoid;
  text-box: normal;
}
</style>

<style>
/* Without `scoped`: these lift the app frame's limits rather than style the sheet. The frame holds
   its content in a zone of fixed height with hidden overflow, and from such a zone only the first
   page reaches the printer. Keyed to the sheet's presence, so a print of any other screen keeps the
   browser's own behaviour. */
@media print {
  html:has(.print-doc),
  html:has(.print-doc) body,
  html:has(.print-doc) :is(.v-application, .v-application__wrap, .v-main, .main-content, .print-page) {
    height: auto !important;
    min-height: 0 !important;
    overflow: visible !important;
    background: #fff !important;
  }
}

/* A named page: only the sheet's pages take these margins and the page number, a print of any
   other screen keeps the browser's own. The browser's headers and footers — date, tab title,
   address — are its own margin boxes, and only a box the page fills itself takes their place, so
   the rest are filled with nothing: a document's margins carry its page number, not the app's URL. */
@page print-sheet {
  size: A4;
  margin: 18mm 16mm 20mm;

  @top-left { content: ""; }
  @top-center { content: ""; }
  @top-right { content: ""; }
  @bottom-left { content: ""; }
  @bottom-center { content: ""; }

  @bottom-right {
    content: counter(page) " / " counter(pages);
    font-size: 8pt;
    color: #8a8a8a;
  }
}
</style>
