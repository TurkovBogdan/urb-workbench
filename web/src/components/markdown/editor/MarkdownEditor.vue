<script setup lang="ts">
// The markdown editing zone: Tiptap holds the document model, Vuetify everything visible.
//
// `v-model` is markdown, not the editor's JSON: the body stays the source of truth, and the
// document model exists only while the zone is mounted. Hence the folder's layout — the bridge
// (`bridge/`) is load-bearing, not an implementation detail.
//
// This file does assembly and nothing else: which nodes and behaviours are plugged in, what the
// template shows and what the EDITING CHROME looks like. Document typography is not here — it is
// shared with the viewer and lives in `markdown/shared/document.css`; the ProseMirror element gets
// the same `md-body` class as the renderer's container, so both are served by one rule set.
//
// The feature set (`mode` / `features`) is not styling but the field's contract: a disabled node
// is NOT in the schema, incoming markdown is reduced to match, and the chrome shows exactly what
// will work. Details and the sets themselves — `modes.ts`.
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { EditorContent, useEditor } from '@tiptap/vue-3'
import StarterKit from '@tiptap/starter-kit'
import { Placeholder } from '@tiptap/extension-placeholder'
import DragHandle from '@tiptap/extension-drag-handle-vue-3'
import { IconGripVertical } from '@tabler/icons-vue'
import { EntityRef, FlatBlocks } from './blocks'
import { BlockMoves, DragSource, MarkdownPaste, useDragPreview } from './behavior'
import {
  BubbleToolbar, SlashMenuExtension, SlashMenuPopup, TableControls,
  createSlashItems, useSlashMenu,
} from './controls'
import { docToMarkdown, markdownToDoc } from './bridge'
import { resolveFeatures, type EditorMode, type Feature } from './modes'

const props = withDefaults(defineProps<{
  modelValue: string
  minHeight?: string
  /** A ready-made feature set. `simple` — paragraph, bold, italic and nothing more. */
  mode?: EditorMode
  /** An exact feature list instead of a mode; when set, the mode is ignored entirely. */
  features?: readonly Feature[]
  /** Length limit of the STORED markdown. Unset — no counter. */
  maxLength?: number
  /**
   * The fill level, in percent, from which the counter shows. `0` — always visible while the field
   * is focused. Overflow is shown regardless of the threshold and of focus: a warning that
   * vanishes when you leave the field is useless exactly when it is needed.
   */
  limitThreshold?: number
  /**
   * `outlined` — its own border and surface: the zone stands on its own.
   * `plain` — no border, no background, no side padding: the field sits inside someone else's
   * card, and a second border around it would read as a box in a box.
   */
  variant?: 'outlined' | 'plain'
  /** Read-only: the document is visible and selectable but does not change. */
  readonly?: boolean
  /** Placeholder on an empty line. Unset — the shared "Type / for commands…". */
  placeholder?: string
  /** The zone's name for assistive technology: a form field has its own, not "editor". */
  ariaLabel?: string
  /**
   * The field label. Sits ABOVE the zone rather than floating in the border as in Vuetify: a
   * floating label lives inside an `input`, while here the inside is a document, and a label over
   * it would cover the first line.
   */
  label?: string
  /** A note under the field: what goes in here, if the field name does not make it obvious. */
  hint?: string
}>(), {
  minHeight: '320px',
  mode: 'full',
  features: undefined,
  maxLength: undefined,
  limitThreshold: 0,
  variant: 'outlined',
  readonly: false,
  placeholder: undefined,
  ariaLabel: undefined,
  label: undefined,
  hint: undefined,
})

// The set is resolved once: changing features on the fly would mean rebuilding the schema under a
// document that already lives in it.
const features = resolveFeatures(props.mode, props.features)
const has = (feature: Feature): boolean => features.has(feature)

// An outward `blur` is needed by forms that save when the field is left: Tiptap has no such event
// of its own, and listening for focus on the container is useless — the nested contenteditable is
// what gets edited.
const emit = defineEmits<{
  'update:modelValue': [value: string]
  blur: []
  focus: []
}>()

const { t } = useI18n()

const slash = useSlashMenu()

// Live region: the only working channel to a screen reader — the drag ARIA attributes
// (`aria-grabbed`, `aria-dropeffect`) were deprecated back in ARIA 1.1, and nothing replaced them.
// Messages speak in POSITIONS, not indexes: "position 3 of 39" makes sense to a person,
// "index 2" does not. Polite mode, so announcements do not interrupt reading.
const announcement = ref('')

// The block under the handle. Move commands work from the selection, so before the menu opens the
// selection is moved here — which also answers "what did I grab".
const handlePos = ref<number | null>(null)
const moveMenu = ref(false)
const moveAt = ref<[number, number]>([0, 0])

// Transaction counter. The editor is not a reactive object, and the floating toolbar learns about
// caret changes only through this number: it is also what moves the toolbar to a new selection.
const tick = ref(0)

// The last markdown this component produced. Comparing against it is what keeps the two
// directions from chasing each other: a value coming back unchanged is our own echo.
let mine = props.modelValue
let syncing = false

// ── Length limit ──────────────────────────────────────────────────────────────

// Count the STORED markdown, not the visible text: the limit sits on a database column, and what
// must be measured is what goes into it — heading hashes, table pipes and escaping included.
const chars = ref(props.modelValue.length)
const focused = ref(false)

const over = computed(() => props.maxLength !== undefined && chars.value > props.maxLength)

const showLimit = computed(() => {
  if (props.maxLength === undefined) return false
  if (over.value) return true
  if (!focused.value) return false
  return chars.value / props.maxLength * 100 >= props.limitThreshold
})

const editor = useEditor({
  content: markdownToDoc(props.modelValue, features),
  // The same class as the renderer's container: document typography comes from the shared file,
  // and editor/viewer parity becomes a structural property rather than a discipline.
  editorProps: {
    attributes: {
      class: 'md-body',
      // The label above the field is plain text with no link to the editing zone; the name for
      // assistive technology is taken from it too, so it need not be passed twice.
      ...(props.ariaLabel ?? props.label ? { 'aria-label': props.ariaLabel ?? props.label ?? '' } : {}),
    },
  },
  extensions: [
    StarterKit.configure({
      // Markdown has no underline. Offering the button would let a user create formatting the
      // body cannot store — the editor must not be able to express more than the format.
      underline: false,
      // `false` disables a node or mark ENTIRELY — it is absent from the schema, not hidden from
      // the toolbar.
      heading: has('heading') ? undefined : false,
      codeBlock: has('codeBlock') ? undefined : false,
      horizontalRule: has('divider') ? undefined : false,
      bold: has('bold') ? undefined : false,
      italic: has('italic') ? undefined : false,
      strike: has('strike') ? undefined : false,
      // The same class the renderer marks inline code with: one rule for both zones.
      code: has('code') ? { HTMLAttributes: { class: 'md-codespan' } } : false,
      link: has('link') ? { openOnClick: false, autolink: true } : false,
      // StarterKit's tree-shaped nodes are disabled entirely: list, item and quote come flat from
      // blocks/. Both sets cannot coexist — a paste from the clipboard would build a tree.
      blockquote: false,
      bulletList: false,
      orderedList: false,
      listItem: false,
      listKeymap: false,
      // The insertion line: 2 px and the selected-border colour — values from Atlassian's design
      // framework. It answers "where will it land", and in a single container that is the only
      // signal needed: a background fill is added only when there are several competing zones.
      // `color: false` — the colour comes only from the class, hence from the theme token, and
      // survives switching to the dark theme; an inline style would have to be duplicated.
      dropcursor: { width: 2, color: false, class: 'editor__dropcursor' },
    }),
    FlatBlocks.configure({ quote: has('quote'), list: has('list'), table: has('table') }),
    // The placeholder on an empty line — wherever the caret is (`showOnlyCurrent` by default),
    // not only in an empty document. The text is a function, not a string: that way it is taken
    // from the dictionary on every render and survives a language switch instead of freezing on
    // whatever it was when the editor was created.
    // Our default placeholder mentions commands via "/", but only where the slash menu exists:
    // in a field without it (simple mode) it would promise something that is not there.
    Placeholder.configure({
      placeholder: () =>
        props.placeholder ??
        t(has('slash') ? 'common.editor.placeholder' : 'common.editor.placeholder_plain'),
    }),
    // Paste must know the feature set just as loading does: the clipboard is how things the
    // field's schema does not know get into it.
    MarkdownPaste.configure({ features }),
    // Block moves come bundled with the handle: without block constructs there is nothing to
    // rearrange, and the SC 2.5.7 alternative path is needed exactly where dragging exists.
    ...(has('handle')
      ? [
          DragSource,
          BlockMoves.configure({
            onAnnounce: (position, total) => {
              announcement.value = t('common.editor.move.announce', { position, total })
            },
          }),
        ]
      : []),
    ...(has('entityRef') ? [EntityRef] : []),
    // The list is built by a function: labels come from the dictionary and survive a language switch.
    ...(has('slash')
      ? [SlashMenuExtension.configure({
          controller: slash.controller,
          items: () => createSlashItems(t, features),
        })]
      : []),
  ],
  onUpdate: ({ editor }) => {
    if (syncing) return
    mine = docToMarkdown(editor.getJSON())
    chars.value = mine.length
    emit('update:modelValue', mine)
  },
  onTransaction: () => { tick.value += 1 },
  onFocus: () => { focused.value = true; emit('focus') },
  onBlur: () => { focused.value = false; emit('blur') },
  editable: !props.readonly,
})

// Read-only mode comes from outside and may change on a live editor — e.g. when the task is
// deleted without reloading the page.
watch(() => props.readonly, (value) => editor.value?.setEditable(!value))

const drag = useDragPreview(editor, handlePos)

watch(() => props.modelValue, (value) => {
  if (value === mine || !editor.value) return
  syncing = true
  editor.value.commands.setContent(markdownToDoc(value, features))
  syncing = false
  mine = value
  chars.value = value.length
})

onBeforeUnmount(() => {
  drag.dispose()
  editor.value?.destroy()
})

function onDragStart(event: DragEvent): void {
  // A layer anchored to the entity is supposed to close when a drag starts.
  moveMenu.value = false
  drag.start(event)
}

function onHandleNode({ pos }: { pos: number }): void {
  handlePos.value = pos
}

// A click on the handle opens the menu of outcomes. This is the SC 2.5.7 alternative: the same
// result with a single pointer press, without dragging. A block has no separate "…" button, so
// the handle itself becomes the menu button — one entity must not have two triggers.
function openMoveMenu(event: Event): void {
  const rect = (event.currentTarget as HTMLElement).getBoundingClientRect()
  moveAt.value = [Math.round(rect.right), Math.round(rect.bottom)]
  if (handlePos.value !== null) editor.value?.commands.setNodeSelection(handlePos.value)
  moveMenu.value = true
}

function move(target: 'up' | 'down' | 'start' | 'end'): void {
  editor.value?.chain().focus().moveBlock(target).run()
  moveMenu.value = false
}
</script>

<template>
  <div class="editor-field">
    <span v-if="props.label" class="editor-field__label">{{ props.label }}</span>

    <div
      class="editor"
      :class="[
        `editor--${props.variant}`,
        { 'is-dragging': drag.dragging.value, 'editor--readonly': props.readonly },
      ]"
      @dragstart="onDragStart"
      @dragend="drag.end"
      @drop="drag.end"
    >
      <!-- The drag handle is an open extension in Tiptap 3 — it renders nothing by itself, so
           the grip below is ours and follows the block under the pointer. -->
      <DragHandle
        v-if="editor && has('handle')"
        :editor="editor"
        class="editor__grip"
        role="button"
        tabindex="0"
        aria-haspopup="menu"
        :aria-label="t('common.editor.move.handle')"
        :aria-expanded="moveMenu"
        :on-node-change="onHandleNode"
        @click="openMoveMenu"
        @keydown.enter.prevent="openMoveMenu"
        @keydown.space.prevent="openMoveMenu"
      >
        <IconGripVertical :size="16" />
      </DragHandle>

      <VMenu v-if="has('handle')" v-model="moveMenu" :target="moveAt" location="bottom start">
        <VList density="compact" nav>
          <VListItem @click="move('start')"><VListItemTitle>{{ t('common.editor.move.start') }}</VListItemTitle></VListItem>
          <VListItem @click="move('up')">
            <VListItemTitle>{{ t('common.editor.move.up') }}</VListItemTitle>
            <template #append><span class="editor__hint">Alt ↑</span></template>
          </VListItem>
          <VListItem @click="move('down')">
            <VListItemTitle>{{ t('common.editor.move.down') }}</VListItemTitle>
            <template #append><span class="editor__hint">Alt ↓</span></template>
          </VListItem>
          <VListItem @click="move('end')"><VListItemTitle>{{ t('common.editor.move.end') }}</VListItemTitle></VListItem>
        </VList>
      </VMenu>

      <EditorContent
        :editor="editor"
        class="editor__body"
        :style="{
          minHeight: props.minHeight,
          // The handle column is needed only where there is a handle: without block constructs
          // it would be an empty strip pushing the text away from the edge for nothing.
          '--editor-rail': has('handle') ? '24px' : '0px',
        }"
      />

      <!-- The counter sits in the bottom padding strip and is absolutely positioned: appearing
           and disappearing with focus, it must not move a single line of text. -->
      <div v-if="showLimit" class="editor__limit" :class="{ 'is-over': over }">
        {{ chars }} / {{ props.maxLength }}
      </div>

      <SlashMenuPopup v-if="has('slash')" :state="slash.state" :controller="slash.controller" />
      <BubbleToolbar :editor="editor" :tick="tick" :features="features" />
      <TableControls v-if="has('table')" :editor="editor" :tick="tick" />

      <div v-if="has('handle')" class="editor__live" role="status" aria-live="polite">{{ announcement }}</div>
    </div>

    <span v-if="props.hint" class="editor-field__hint">{{ props.hint }}</span>
  </div>
</template>

<!-- Document typography. The renderer includes the same file — Vite merges them into one asset,
     and no copy appears in the build.
     EVERY consumer must include it: without this line the editing zone would get its styles only
     on pages where a renderer happened to be nearby — and would look one way or another depending
     on its neighbour. -->
<style src="../shared/document.css"></style>

<style scoped>
/* Editing chrome only. What the TEXT looks like is a question for the document, not the editor,
   and there is one answer for both zones: `markdown/shared/document.css`. */

/* The field wrapper: label, zone, hint. It carries no geometry of its own — it exists only so the
   label and hint sit in the same flow as the zone. */
.editor-field {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

/* A label above the field, not Vuetify's floating label: there the label lives inside an `input`,
   here the inside is a document, and a label over it would cover the first line. Size and colour
   match field labels elsewhere in the interface. */
.editor-field__label {
  font-size: 12px;
  line-height: 1.2;
  color: var(--text-muted);
}

.editor-field__hint {
  font-size: 11px;
  line-height: 1.3;
  color: var(--text-faint);
}

.editor {
  /* Reference frame for the length counter: it sits in the bottom padding strip, not in the flow. */
  position: relative;
}

.editor--outlined {
  background: var(--surface);
  border: 1px solid var(--border-soft);
  border-radius: var(--radius);
  overflow: hidden;
  transition: border-color 160ms ease;
}

/* A field inside someone else's card: the card provides border and surface, and its padding the
   side spacing. Our own would add to it, and the field's text would misalign with the section
   heading above. */
.editor--plain .editor__body {
  --editor-gutter: 0px;

  padding: 2px 0 20px;
}

/* While a drag is in progress the zone says so itself: an accent border with a soft halo. A
   background fill would be a mistake here — it is reserved for when there are several drop zones
   and the question is "which one", while we have a single container. */
.editor--outlined.is-dragging {
  border-color: color-mix(in srgb, rgb(var(--v-theme-primary)) 35%, var(--border-soft));
}

/* Editing is unavailable — the cursor says so. The text must not be dimmed: it is being read, and
   a deleted task must stay readable. */
.editor--readonly :deep(.ProseMirror) {
  cursor: default;
}

/* The handle is the only grab area, so it is at least 24×24 CSS pixels: SC 2.5.8 Target Size
   (AA). The visible icon is smaller; the hit area is made up by the size of the handle itself.
   `touch-action: none` is the only lever against page scrolling: browsers no longer let
   preventDefault cancel panning, and the property must be set on the smallest possible area, or
   a finger will stop scrolling the list. */
.editor__grip {
  display: flex;
  align-items: center;
  justify-content: center;
  min-width: 26px;
  min-height: 26px;
  border-radius: 4px;
  color: var(--text-faint);
  cursor: grab;
  opacity: 0.75;
  touch-action: none;
}

/* A visible focus ring is part of the keyboard model, not decoration. */
.editor__grip:focus-visible {
  outline: 2px solid rgb(var(--v-theme-primary));
  outline-offset: 2px;
  opacity: 1;
}

.editor__grip:hover {
  background: color-mix(in srgb, rgb(var(--v-theme-on-surface)) 8%, transparent);
  opacity: 1;
}

.editor__grip:active {
  cursor: grabbing;
}

/* `position: relative` is not cosmetic here: prosemirror-dropcursor attaches the insertion line to
   the editor's `offsetParent`. Without a positioned ancestor it ended up in the app root —
   outside this component's scoped styles — and rendered transparent. This is also the containing
   block: the line computes its coordinates from this element. */
.editor__body {
  /* The paddings are named variables because the insertion line is computed from them: it must
     coincide with the text column, not be fitted to it by hand.
     `--editor-rail` comes from the template: without a drag handle there is no need for its
     column, and the text starts right after the zone's padding. The value here is a fallback.
     The sum of these two is NOT arbitrary. The extension places the handle at the block's left
     edge with its own 10px gap; with a 26px handle (24 minimum per SC 2.5.8 Target Size) it
     needs 36px to the left of the text. Less, and the handle slides past the zone's edge where
     `overflow: hidden` clips it: the icon stays visible while the hit area silently loses a few
     pixels — breaking exactly what the size was chosen for. */
  --editor-gutter: 14px;
  --editor-rail: 24px;

  position: relative;
  padding: 16px var(--editor-gutter) 28px;
}

/* The caret needs the outline removed, and the drag handle column must lie INSIDE `.ProseMirror`:
   otherwise moving the mouse towards the handle would take the pointer out of the zone the plugin
   listens to, and the handle would vanish on approach — impossible to grab. */
.editor__body :deep(.ProseMirror) {
  outline: none;
  padding-left: var(--editor-rail);
}

/* ── Table in the editor ─────────────────────────────────── */

/* An empty cell never occurs in the viewer, but in the editor it is a normal state — a freshly
   added column is empty throughout. Without a minimum such a cell collapses to zero and there is
   no way to put the caret into it. The value is roughly one word. */
.editor__body :deep(.md-table :is(th, td)) {
  min-width: 5ch;
}

/* The cell under the caret — so that in a wide table you can see where you are editing.
   Background only: a border would shift neighbouring cells' content by a pixel. */
.editor__body :deep(.md-table :is(th, td):focus-within) {
  background: color-mix(in srgb, rgb(var(--v-theme-primary)) 7%, transparent);
}

/* The scroll wrapper must not clip the cell highlight at the table's edge. */
.editor__body :deep(.md-table-wrap) {
  scrollbar-width: thin;
}

/* ── What was grabbed ────────────────────────────────────── */

/* The block the handle selected before opening the menu is highlighted — it answers "what did I
   grab" when there is no drag yet.
   DURING a drag there is no highlight: the block stays exactly as it was. There is no reason to
   restyle the source — the card under the pointer already shows what is moving, and the document
   beneath must stay unchanged so it shows where to aim.
   Top-level blocks only: `ProseMirror-selectednode` is also put on a selected atom — the entity
   pill — which has its own highlight, and two on top of one small chip turn into mush. */
.editor:not(.is-dragging) .editor__body :deep(.ProseMirror > .ProseMirror-selectednode) {
  background: color-mix(in srgb, rgb(var(--v-theme-primary)) 9%, transparent);
}

/* ── Insertion line ──────────────────────────────────────── */

/* The insertion line is just a line: thin, solid, accent-coloured. No glow, no shadows, no
   rounding, no end caps. Thickness comes from the extension's `width` option, colour from this
   class. Position animates smoothly so the line glides between gaps rather than teleporting. */
.editor__body :deep(.editor__dropcursor) {
  background-color: rgb(var(--v-theme-primary));
  border-radius: 0;
  /* The plugin takes the width from the target block, and our blocks differ in width: paragraphs
     and headings have the measure, a code block and a divider do not. So the line jumped from
     block to block. We set it to the text column instead: the insertion point is a property of
     the document, not of whichever block it happens to be next to.
     The horizontal is measured from `.editor__body`: for absolute positioning that is its
     padding box, so the zone's padding and the handle column add up on the left. */
  left: calc(var(--editor-gutter) + var(--editor-rail)) !important;
  right: var(--editor-gutter) !important;
  width: auto !important;
  max-width: var(--reading-measure, 92ch);
  transition:
    top 120ms ease,
    left 120ms ease,
    width 120ms ease;
}

@media (prefers-reduced-motion: reduce) {
  .editor__body :deep(.editor__dropcursor) { transition-duration: 1ms; }
}

/* ── Source during a drag ────────────────────────────────── */

/* Dimmed but kept in place: it shows where the thing was taken from and where it returns if no
   drop target is chosen. Removing the block from the flow during a drag is not allowed — the list
   would collapse, the neighbours would jump, and the point of reference would be lost. The 0.4
   value comes from the canon.
   The `.is-dragging` condition guards against a stuck class: without a drag there is nothing to
   dim. */
.editor.is-dragging .editor__body :deep(.is-drag-source) {
  opacity: 0.4;
}

.editor__body :deep(.is-drag-source) {
  transition: opacity 120ms ease;
}

@media (prefers-reduced-motion: reduce) {
  .editor__body :deep(.is-drag-source) { transition-duration: 1ms; }
}

/* ── Preview under the pointer ───────────────────────────── */

/* The card follows the pointer on its own: the native preview is disabled with a transparent
   pixel because the platform draws it with its own translucency. It lives in the editing zone's
   tree, so text styles reach the clone by the same rules as the document itself; `fixed` is not
   clipped by the editor card's `overflow: hidden`. Positioned by transform only. */
.editor__body :deep(.editor__preview) {
  position: fixed;
  top: 0;
  left: 0;
  z-index: 3000;
  opacity: 1;
  /* Room for the shadow: the snapshot is bounded by the element's box, and without a margin the
     shadow would be clipped at the card's edge. The margin is sized by the blur radius. */
  padding: 26px;
  pointer-events: none;
}

.editor__body :deep(.editor__preview-card) {
  background: var(--surface);
  border: 1px solid var(--border-soft);
  border-radius: var(--radius);
  /* The card's padding is not part of the inner document's width: the width is carried by the
     `preview-doc` layer and must not be altered by padding — line breaks depend on it. */
  padding: 14px 18px;
  width: fit-content;
  /* Neither width nor height is clipped: a clipped card lies about what is moving. */
  /* The shadow is set explicitly: Vuetify's elevation utilities do not make it into this build,
     and the snapshot is taken from the actually rendered element — a class that does not exist
     would not show up. Two shadows: the far one gives height, the near one outlines the edge. */
  box-shadow:
    0 14px 30px -10px rgb(0 0 0 / 0.32),
    0 4px 10px -4px rgb(0 0 0 / 0.18);
}

/* A clone of the editable document, not of a viewer body: the shared file removes `pre-wrap` from
   every `md-body` except ProseMirror itself — here it has to be restored. Otherwise consecutive
   typed spaces collapse, lines reflow, and the card's height diverges from the original — the
   very thing the preview is built to match. */
.editor__body :deep(.editor__preview-doc) {
  white-space: pre-wrap;
}

/* Margins between blocks inside the preview are NOT touched: they must be exactly those of the
   document, or the card's height diverges from the original. The first and last block are the
   exception: the card must hug its content. */
.editor__body :deep(.editor__preview-doc > :last-child) { margin-bottom: 0; }

/* ── Move confirmation ───────────────────────────────────── */

/* A 700 ms flash on the moved block: after a move the eye loses the object among its neighbours,
   and without confirmation it is unclear whether it landed where intended. Background only — no
   size or layout changes: only `transform` and `opacity` are acceptable in motion, anything else
   costs frames. */
.editor__body :deep(.is-moved) {
  animation: move-flash 700ms cubic-bezier(0.25, 0.1, 0.25, 1);
  border-radius: 4px;
}

@keyframes move-flash {
  from { background-color: color-mix(in srgb, rgb(var(--v-theme-primary)) 20%, transparent); }
  to   { background-color: transparent; }
}

@media (prefers-reduced-motion: reduce) {
  .editor__body :deep(.is-moved) { animation-duration: 1ms; }
  .editor { transition-duration: 1ms; }
}

/* The live region must stay in the flow and outside a re-rendered subtree, so it is hidden by
   offset rather than `display: none` — a screen reader does not read content hidden that way. */
.editor__live {
  position: absolute;
  width: 1px;
  height: 1px;
  margin: -1px;
  padding: 0;
  overflow: hidden;
  clip-path: inset(50%);
  white-space: nowrap;
}

.editor__hint {
  font-family: var(--font-mono);
  font-size: 10px;
  color: var(--text-faint);
  padding-left: 16px;
}

/* ── Length limit ────────────────────────────────────────── */

/* Absolutely positioned in the zone's bottom padding strip: the counter appears and disappears
   with focus and has no right to move the text while doing so. Monospaced, because the number
   grows one character at a time, and a proportional font would make the line jitter on every
   digit. */
.editor__limit {
  position: absolute;
  right: 10px;
  bottom: 6px;
  font-family: var(--font-mono);
  font-size: 11px;
  line-height: 1;
  color: var(--text-faint);
  font-variant-numeric: tabular-nums;
  pointer-events: none;
  user-select: none;
}

/* Overflow is not a shade but a different state: text past the limit will not reach the database,
   and that must be said in the same colour the app uses for a refusal. */
.editor__limit.is-over {
  color: rgb(var(--v-theme-error));
  font-weight: 500;
}

/* The placeholder is a decoration, so it is styled rather than rendered as content. A zero-height
   `float` keeps it from affecting layout: the line stays empty both in height and in caret
   position. Top-level blocks only: in an empty list item the placeholder would be noise. */
.editor__body :deep(.ProseMirror > .is-empty)::before {
  content: attr(data-placeholder);
  float: left;
  height: 0;
  pointer-events: none;
  color: var(--text-faint);
}
</style>
