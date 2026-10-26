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
import { computed, nextTick, onBeforeUnmount, provide, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import ImageGallery from '@/components/files/ImageGallery.vue'
import { EditorContent, useEditor } from '@tiptap/vue-3'
import StarterKit from '@tiptap/starter-kit'
import { Placeholder } from '@tiptap/extension-placeholder'
import {
  DragHandlePlugin,
  defaultComputePositionConfig,
  dragHandlePluginDefaultKey,
  normalizeNestedOptions,
} from '@tiptap/extension-drag-handle'
import { IconGripVertical } from '@tabler/icons-vue'
import { CodeBlock, Diagram, EntityRef, FlatBlocks, OPEN_PICTURE } from './blocks'
import {
  BlockMoves,
  continueBelow,
  DragSource,
  DOCUMENT_REPLACED,
  DropSlot,
  FileAttach,
  LENGTH_LIMIT_BYPASS,
  LengthLimit,
  MarkdownPaste,
  handleTop,
  useBlockMarks,
  useDragPreview,
  type AttachFile,
  type RefuseFile,
} from './behavior'
import { errorText } from '@/api/errorText'
import { useFileDropZone } from '@/composables/useFileDrop'
import { pushToast } from '@/composables/useToasts'
import { droppedPaths } from '@/shared/utils/fileDrop'
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
  /**
   * Hard length limit of the STORED markdown: typing stops at it and a paste is cut to fit (see
   * behavior/lengthLimit.ts). Unset — no limit and no counter.
   */
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
  /**
   * Files pasted or dropped into the field go to the field's holder: upload one and answer with the
   * text it stands for in the body (its code). Unset — a paste and a drop are what they always were.
   * The page knows the holder; see `behavior/fileAttach.ts`.
   *
   * With it the field is a drop zone of the window (`composables/useFileDrop.ts`) — marked while
   * files are over the window, filled under the pointer — and the slash menu offers a file dialog.
   */
  attach?: AttachFile
  /** A file the holder will not take, known before sending (over the size ceiling): the reason. */
  refuse?: RefuseFile
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
  attach: undefined,
  refuse: undefined,
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

// ── Files ─────────────────────────────────────────────────────────────────────
// A file has somewhere to go only in a field that shows codes, has a holder and is being edited.
const takesFiles = computed(() => has('entityRef') && Boolean(props.attach) && !props.readonly)

// The slash command's dialog. Clicked inside the key press or the click that picked the command —
// a browser opens a file dialog only in a gesture. The caret stays where the `/` was while the
// dialog is open: nothing edits the field meanwhile, so the files land there.
const filePicker = ref<HTMLInputElement | null>(null)

function pickFile(): void {
  filePicker.value?.click()
}

function filesPicked(event: Event): void {
  const input = event.target as HTMLInputElement
  const files = Array.from(input.files ?? [])
  // The same file picked again must fire `change` again.
  input.value = ''
  if (files.length) editor.value?.chain().focus().attachFiles(files).run()
}

// One full-screen viewer for every picture of the document (`blocks/entityRef/EntityImageView.vue`). It takes
// the focus while open, so the arrows that page through a gallery do not also move the caret.
//
// Closed, it hands the focus back to the field, on the picture it was opened from — selected, so
// the person carries on where they were: Enter opens it again, the arrows step on from it. Its
// position is asked when the viewer closes: the text may have changed meanwhile.
const lightbox = ref<string | null>(null)
const lightboxCodes = ref<string[]>([])
let openedAt: (() => number | undefined) | null = null

provide(OPEN_PICTURE, (code, gallery, at) => {
  lightboxCodes.value = gallery
  lightbox.value = code
  openedAt = at
})

watch(lightbox, (code) => {
  if (code !== null || !openedAt) return
  const at = openedAt
  openedAt = null
  // After the dialog's own close: it puts the focus back where it was taken from, and the selection
  // must land after that.
  void nextTick(() => {
    const pos = at()
    const current = editor.value
    if (pos === undefined || !current || current.isDestroyed) return
    current.chain().focus().setNodeSelection(pos).run()
  })
})

// Live region: the only working channel to a screen reader — the drag ARIA attributes
// (`aria-grabbed`, `aria-dropeffect`) were deprecated back in ARIA 1.1, and nothing replaced them.
// Messages speak in POSITIONS, not indexes: "position 3 of 39" makes sense to a person,
// "index 2" does not. Polite mode, so announcements do not interrupt reading.
const announcement = ref('')

// A picture is being dragged (`blocks/entityRef/pictureDrag.ts`): the block handle and the marks
// stay out of it, as they do for a block drag.
const pictureDragging = ref(false)

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

// The same thresholds as `LimitField`: input stops at the limit, so the counter warns in advance —
// yellow from 70% full, red from 90% — and a cut never comes as a surprise.
const WARNING_FROM = 70
const DANGER_FROM = 90

const over = computed(() => props.maxLength !== undefined && chars.value > props.maxLength)
const fill = computed(() => props.maxLength === undefined ? 0 : chars.value / props.maxLength * 100)

const limitLevel = computed(() => {
  if (fill.value >= DANGER_FROM) return 'is-danger'
  if (fill.value >= WARNING_FROM) return 'is-warning'
  return ''
})

const showLimit = computed(() => {
  if (props.maxLength === undefined) return false
  if (over.value) return true
  if (!focused.value) return false
  return fill.value >= props.limitThreshold
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
    // Blocks move by the handle only. ProseMirror's own drag of a selection — a few words torn out
    // of a paragraph, a pill, a stretch of code — went around everything the handle draws (source
    // mark, insertion line, preview) and read as a glitch. The handle sits outside the editable
    // root, so its drag never reaches this handler; text still moves by cut and paste, and a drop
    // from outside is a `drop`, not a `dragstart`, so it is left alone.
    handleDOMEvents: {
      dragstart: (_view, event) => {
        event.preventDefault()
        return true
      },
    },
    // A drop that brings only the files' addresses on the disk, not the files (`droppedPaths`) —
    // some apps hand a dragged file over that way — would be typed in as `file:///…`. Taken here, in
    // every field and ahead of the file handling, so a field that takes no files does not type it
    // either; the field says what happened instead.
    handleDrop: (_view, event, _slice, moved) => {
      const data = event.dataTransfer
      if (moved || !data || Array.from(data.items ?? []).some((item) => item.kind === 'file')) return false
      const paths = droppedPaths(data)
      if (!paths.length) return false
      event.preventDefault()
      pushToast(
        takesFiles.value
          ? t('common.file_drop.path_only', { name: paths.join(', ') })
          : t('common.file_drop.not_here'),
        'warn',
      )
      return true
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
      // Always off: the code block is our own (blocks/codeBlock.ts), added below under the same name.
      codeBlock: false,
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
      // The editor shows what is stored, and markdown stores no empty paragraph. TrailingNode kept
      // one after a closing list, table, code block or diagram that no key could delete — the same
      // transaction put it back. Writing past the last block goes through each block's own exit:
      // Enter in an empty item, Mod-Enter or ArrowDown out of code, ArrowDown into the gap after a
      // table, diagram or rule — and a press below the text (`behavior/continueBelow.ts`).
      trailingNode: false,
      // The insertion line: 2 px and the selected-border colour — values from Atlassian's design
      // framework. It answers "where will it land", and in a single container that is the only
      // signal needed: a background fill is added only when there are several competing zones.
      // `color: false` — the colour comes only from the class, hence from the theme token, and
      // survives switching to the dark theme; an inline style would have to be duplicated.
      dropcursor: { width: 2, color: false, class: 'editor__dropcursor' },
    }),
    FlatBlocks.configure({ quote: has('quote'), list: has('list'), table: has('table') }),
    ...(has('codeBlock') ? [CodeBlock] : []),
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
    // Files on the clipboard or in a drop go to the page's `attach`, ahead of the text paste. Only
    // a field that can show a code takes them: the code is what the file becomes in the text.
    ...(has('entityRef')
      ? [FileAttach.configure({
          attach: () => props.attach,
          refuse: () => props.refuse,
          contentFor: (text, state) => {
            const block = state.schema.nodeFromJSON(markdownToDoc(text, features)).firstChild
            return block?.isTextblock ? block.content : null
          },
          label: (done, total) => total === 1
            ? t('common.editor.attach.uploading_one')
            : t('common.editor.attach.uploading', { done, total }),
          onFailure: (error) => pushToast(errorText(error)),
          onRefused: (reason) => pushToast(reason),
          onFolders: () => pushToast(t('common.file_drop.folder'), 'warn'),
          onNoRoom: () => pushToast(t('common.editor.attach.no_room'), 'warn'),
          onNotInserted: () => pushToast(t('common.editor.attach.not_inserted'), 'warn'),
        })]
      : []),
    // Paste must know the feature set just as loading does: the clipboard is how things the
    // field's schema does not know get into it.
    MarkdownPaste.configure({ features }),
    // The limit is hard: typing stops at it and a paste is cut to fit, as in a native field.
    LengthLimit.configure({ maxLength: props.maxLength }),
    // Block moves come bundled with the handle: without block constructs there is nothing to
    // rearrange, and the SC 2.5.7 alternative path is needed exactly where dragging exists.
    ...(has('handle')
      ? [
          DragSource,
          DropSlot,
          BlockMoves.configure({
            onAnnounce: (position, total) => {
              announcement.value = t('common.editor.move.announce', { position, total })
            },
          }),
        ]
      : []),
    ...(has('entityRef')
      ? [EntityRef.configure({
          images: has('image'),
          onAnnounce: ({ position, total }) => {
            announcement.value = t('common.editor.picture.announce', { position, total })
          },
          onDragging: (on) => { pictureDragging.value = on },
        })]
      : []),
    ...(has('diagram') ? [Diagram] : []),
    // The list is built by a function: labels come from the dictionary and survive a language switch.
    ...(has('slash')
      ? [SlashMenuExtension.configure({
          controller: slash.controller,
          items: () => createSlashItems(t, features, { pickFile: takesFiles.value ? pickFile : undefined }),
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

/** The handle's box, see `.editor__grip`. The resting marks are laid out with it. */
const GRIP_SIZE = { width: 20, height: 26 }

// The frame both the live handle and the resting marks are positioned against (`.editor`). It is
// also the field's drop zone for files: the window's guard asks it whether it takes them.
const frame = ref<HTMLElement | null>(null)
const fileZone = useFileDropZone(frame, () => takesFiles.value)
const marks = useBlockMarks(editor, frame, computed(() => has('handle') && !props.readonly), tick, GRIP_SIZE)

// One glyph per block, never two. At rest a block shows its mark, and the live handle on top of it
// is an empty grab area; the handle draws its own glyph only while it is the thing being used —
// under the pointer, focused from the keyboard, its menu open, a drag running — and the mark under
// it steps aside. Two glyphs stacked on the same pixels read as one bolder icon.
const gripHovered = ref(false)
const gripFocused = ref(false)
// While a block or a picture is being dragged nothing under the pointer answers it — not the
// handle, not a block's mark: a highlight then reads as "drop here", and the drop place is the
// slot's or the line's to show. The pointer's hover flag is also stale by then: a drag delivers no
// `mouseleave`.
const dragging = computed(() => drag.dragging.value || pictureDragging.value)
const gripLit = computed(() =>
  !dragging.value && (gripHovered.value || gripFocused.value || moveMenu.value))

// The block under the pointer brings its mark up to full strength: the handle the pointer is
// heading for stands out of the faint column. `handlePos` already follows the pointer from block
// to block; this says whether the pointer is in the zone at all.
const zoneHovered = ref(false)

watch(() => props.modelValue, (value) => {
  if (value === mine || !editor.value) return
  syncing = true
  // The value comes from the database: it is shown as stored, even longer than the limit. It is
  // another text now, and a file still uploading has no place in it (`behavior/fileAttach.ts`).
  editor.value
    .chain()
    .setMeta(LENGTH_LIMIT_BYPASS, true)
    .setMeta(DOCUMENT_REPLACED, true)
    .setContent(markdownToDoc(value, features))
    .run()
  syncing = false
  mine = value
  chars.value = value.length
})

// The live handle's plugin, registered here rather than through `extension-drag-handle-vue-3`:
// that wrapper does not pass `dragImageProperties` on. Left unset, the plugin builds the native
// drag image by cloning the block and copying EVERY computed CSS property onto every element of
// the clone — on a code block, hundreds of tokens plus the language list's hidden <select> with
// its 230 options: 888ms frozen at the start of each drag. The native image is thrown away anyway
// (`useDragPreview` swaps in a transparent pixel and draws its own card), so nothing is copied.
const grip = ref<HTMLElement | null>(null)
let gripPlugin: ReturnType<typeof DragHandlePlugin> | null = null

watch([editor, grip], ([current, element]) => {
  if (gripPlugin || !current || current.isDestroyed || !element) return
  element.style.visibility = 'hidden'
  gripPlugin = DragHandlePlugin({
    editor: current,
    element,
    pluginKey: dragHandlePluginDefaultKey,
    computePositionConfig: { ...defaultComputePositionConfig, ...gripPosition },
    onNodeChange: onHandleNode,
    nestedOptions: normalizeNestedOptions(false),
    dragImageProperties: [],
  })
  current.registerPlugin(gripPlugin.plugin)
}, { flush: 'post' })

onBeforeUnmount(() => {
  if (gripPlugin && editor.value && !editor.value.isDestroyed) {
    editor.value.unregisterPlugin(dragHandlePluginDefaultKey)
  }
  gripPlugin?.unbind()
  gripPlugin = null
  drag.dispose()
  editor.value?.destroy()
})

// Only a drag that starts on the handle is a block drag with our own card and source marking; a drag
// starting in the text is cancelled before it begins (`handleDOMEvents.dragstart` above), so the
// guard here is what keeps a drop from outside out of the block-drag bookkeeping.
function onDragStart(event: DragEvent): void {
  // A layer anchored to the entity is supposed to close when a drag starts.
  moveMenu.value = false
  if (!(event.target as Element | null)?.closest?.('.editor__grip')) return
  drag.start(event)
}

// The block under the pointer, kept for the positioning step below. The extension reports the
// node before it positions the handle, so the element is current by the time it is measured.
let handleBlock: HTMLElement | null = null

function onHandleNode({ pos }: { pos: number }): void {
  handlePos.value = pos
  const dom = editor.value?.view.nodeDOM(pos)
  handleBlock = dom instanceof HTMLElement ? dom : null
}

// The extension pins the handle to the block's top edge (`left-start`), and blocks start their
// first line at different depths: a heading's line is taller than the handle, a code block opens
// with a header, a diagram with its picture. Measured, the icon sat 5.5px off a heading's line and
// 6.6px off a code header. This step moves the handle to where `handleTop` puts it — the same
// point the resting marks below are drawn at.
const gripPosition = {
  middleware: [
    {
      name: 'firstLine',
      fn: ({ y, rects }: { y: number; rects: { floating: { height: number } } }) =>
        handleBlock ? { y: y + handleTop(handleBlock, rects.floating.height) } : {},
    },
  ],
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

// The empty part of the field below the text continues it: see `behavior/continueBelow.ts`.
function onBodyPress(event: MouseEvent): void {
  if (editor.value) continueBelow(editor.value, event)
}
</script>

<template>
  <div class="editor-field">
    <span v-if="props.label" class="editor-field__label">{{ props.label }}</span>

    <div
      ref="frame"
      class="editor"
      :class="[
        `editor--${props.variant}`,
        {
          'is-dragging': drag.dragging.value,
          'is-picture-dragging': pictureDragging,
          'editor--readonly': props.readonly,
          'editor--limited': props.maxLength !== undefined,
          'editor--handled': has('handle'),
          'editor--file-target': fileZone.armed.value,
          'editor--file-over': fileZone.over.value,
          'editor--file-refused': fileZone.refused.value,
        },
      ]"
      @dragstart="onDragStart"
      @dragend="drag.end"
      @drop="drag.end"
      @mouseenter="zoneHovered = true"
      @mouseleave="zoneHovered = false"
    >
      <!-- A resting handle beside every block, drawn where the live one lands on it. Inert: the
           pointer passes through to the block, and the live handle that then appears on top is
           the one that drags. Decoration for the eye, so hidden from assistive technology — the
           live handle carries the name and the menu. -->
      <div v-if="marks.length" class="editor__marks" aria-hidden="true">
        <span
          v-for="mark in marks"
          :key="mark.pos"
          class="editor__mark"
          :class="{
            'editor__mark--active': zoneHovered && !dragging && mark.pos === handlePos,
            'editor__mark--covered': gripLit && mark.pos === handlePos,
          }"
          :style="{ top: `${mark.top}px`, left: `${mark.left}px` }"
        >
          <IconGripVertical :size="14" :stroke-width="1.8" />
        </span>
      </div>

      <!-- The drag handle is an open extension in Tiptap 3 — it renders nothing by itself, so
           the grip below is ours; the plugin bound to it (`gripPlugin`) moves it to the block
           under the pointer and starts the drag from it. -->
      <div
        v-if="editor && has('handle')"
        ref="grip"
        class="editor__grip"
        :class="{ 'editor__grip--lit': gripLit }"
        style="position: absolute"
        data-dragging="false"
        role="button"
        tabindex="0"
        aria-haspopup="menu"
        :aria-label="t('common.editor.move.handle')"
        :aria-expanded="moveMenu"
        @click="openMoveMenu"
        @mouseenter="gripHovered = true"
        @mouseleave="gripHovered = false"
        @focusin="gripFocused = true"
        @focusout="gripFocused = false"
        @keydown.enter.prevent="openMoveMenu"
        @keydown.space.prevent="openMoveMenu"
      >
        <IconGripVertical :size="14" :stroke-width="1.8" />
      </div>

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
          '--editor-rail': has('handle') ? '20px' : '0px',
        }"
        @mousedown="onBodyPress"
      />

      <!-- The counter sits in the bottom padding strip and is absolutely positioned: appearing
           and disappearing with focus, it must not move a single line of text. -->
      <div v-if="showLimit" class="editor__limit" :class="limitLevel">
        {{ chars }} / {{ props.maxLength }}
      </div>

      <SlashMenuPopup v-if="has('slash')" :state="slash.state" :controller="slash.controller" />
      <input
        v-if="has('slash') && has('entityRef')"
        ref="filePicker"
        type="file"
        multiple
        hidden
        class="editor__file-picker"
        @change="filesPicked"
      >
      <BubbleToolbar :editor="editor" :tick="tick" :features="features" />
      <TableControls v-if="has('table')" :editor="editor" :tick="tick" />

      <div v-if="has('handle') || has('image')" class="editor__live" role="status" aria-live="polite">{{ announcement }}</div>
      <ImageGallery v-if="has('image')" v-model="lightbox" :codes="lightboxCodes" />
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

  /* The look of a block drag, as the editor's own variables. The values are the task list's
     (TaskRows / EntityRowList: placeholder, source, preview), so the gesture reads the same across
     the app; they are named here so the editor can be tuned without touching the lists. */
  --editor-drop-slot-bg: var(--accent-soft);
  --editor-drop-slot-radius: var(--radius-sm);
  --editor-drop-slot-max-height: 48px;
  --editor-drag-source-bg: var(--accent-soft);
  --editor-drag-source-opacity: 0.4;
  --editor-drag-preview-border: var(--border);
  --editor-drag-preview-radius: var(--radius-sm);
  --editor-drag-preview-shadow: 0 12px 32px rgb(0 0 0 / 0.28);
}

.editor--outlined {
  background: var(--surface);
  border: 1px solid var(--border-soft);
  border-radius: var(--radius);
  overflow: hidden;
  transition: border-color 160ms ease;
}

/* A field inside someone else's card: the card provides border and surface, and its padding the
   spacing on every side. Our own would add to it — the text would misalign with the section
   heading above, and under the last line the card would end with a gap twice its top one. */
.editor--plain .editor__body {
  --editor-gutter: 0px;

  padding: 2px 0;
}

/* With handles, though, the text cannot sit on the heading's line: the handle column (`--editor-
   rail`, 20px) comes first. The field borrows 8px of the card's padding for it, so the text sits
   12px right of the heading and the handles stand partly in the padding, still clear of the
   card's edge. Every card that hosts a plain field pads it by 16px — task, note, codex. */
.editor--plain.editor--handled {
  margin-left: -8px;
}

/* Editing is unavailable — the cursor says so. The text must not be dimmed: it is being read, and
   a deleted task must stay readable. */
.editor--readonly :deep(.ProseMirror) {
  cursor: default;
}

/* The handle is the app's other handle in size and look (components/DragHandle.vue, the task
   list): a 20px-wide box around the same 14px glyph, faint at rest, full text colour under the
   pointer, no plate behind it. 20px is under SC 2.5.8's 24, and passes by its spacing exception:
   there is one live handle, and nothing else to hit within 24px of it. It is 26px tall so it spans
   a line of text. Every pixel of width is a pixel the text moves right of its section heading.
   `touch-action: none` is the only lever against page scrolling: browsers no longer let
   preventDefault cancel panning, and the property must be set on the smallest possible area, or
   a finger will stop scrolling the list. */
.editor__grip {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 20px;
  height: 26px;
  border-radius: 4px;
  color: var(--text-faint);
  cursor: grab;
  transition: color 0.12s ease;
  touch-action: none;
}

/* A visible focus ring is part of the keyboard model, not decoration. */
.editor__grip:focus-visible {
  outline: 2px solid rgb(var(--v-theme-primary));
  outline-offset: 2px;
}

.editor__grip:hover {
  color: var(--text);
}

.editor__grip:active {
  cursor: grabbing;
}

/* At rest the live handle is an empty grab area over its block's mark; its glyph shows only while
   it is in use (`--lit`, see `gripLit`), and the mark under it fades out for that time — a
   cross-fade, both on the same 150ms, so the glyph never dips to nothing in between.
   The glyphs fade by COLOUR, never by `opacity`: an opacity transition puts the glyph on a
   compositor layer, the field's text, painted after it and overlapping it, is pushed onto a layer
   too, and Chrome draws text there with greyscale antialiasing instead of subpixel — for the 150ms
   of every fade the whole field's text turned lighter and thinner (TASK@C54172FEEF). A colour
   change is only a repaint. */
.editor__grip :deep(svg) {
  color: transparent;
  transition: color 0.15s ease;
}

.editor__grip--lit :deep(svg) {
  color: inherit;
}

/* The resting marks: the live handle's box and glyph at rest, and nothing to the pointer — a mark
   that took the hover would hide the live handle it stands in for. Fainter than the handle in use:
   one per block runs down the whole document, and at full strength the column competes with the
   text. */
.editor__marks {
  position: absolute;
  inset: 0;
  pointer-events: none;
}

.editor__mark {
  position: absolute;
  display: flex;
  align-items: center;
  justify-content: center;
  width: 20px;
  height: 26px;
  /* 55% of the handle's resting colour; faded by colour, not `opacity` — see `.editor__grip svg`. */
  color: color-mix(in srgb, var(--text-faint) 55%, transparent);
  transition: color 0.15s ease;
}

/* The block under the pointer: its mark at full strength, the handle's own resting colour. */
.editor__mark--active {
  color: var(--text-faint);
}

/* Declared after `--active`: a mark can be both, and covered wins. */
.editor__mark--covered {
  color: transparent;
}

@media (prefers-reduced-motion: reduce) {
  .editor__mark,
  .editor__grip :deep(svg) {
    transition: none;
  }
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
     The rail is NOT arbitrary: it is the handle's width. The extension places the handle flush
     against the block's left edge, so a rail as wide as the handle keeps it inside `.ProseMirror`
     (see the next rule). Narrower, and the handle pokes out into the gutter — where an outlined
     zone's `overflow: hidden` clips its hit area while the icon still shows. */
  --editor-gutter: 14px;
  --editor-rail: 20px;

  position: relative;
  padding: 16px var(--editor-gutter) 28px;
  /* The field's width is what a gallery steps its columns down by (`document.css`): the document
     cannot wrap a gallery in a container of its own, as the viewer does. */
  container-type: inline-size;
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
   pill — which has its own highlight, and two on top of one small chip turn into mush.
   Not a diagram either: a plain click selects it, so the wash would land on every diagram looked
   at; it marks its selection with its own quiet frame (DiagramView.vue). */
.editor:not(.is-dragging) .editor__body :deep(.ProseMirror > .ProseMirror-selectednode:not(.diagram-node)) {
  background: color-mix(in srgb, rgb(var(--v-theme-primary)) 9%, transparent);
}

/* ── Files from the computer ─────────────────────────────── */

/* Two layers over the field, both inert and faded by `opacity` alone. While files are over the
   window, a field that takes them wears a dashed line (`::after`) — the person sees the targets
   before aiming. Under the pointer it also fills (`::before`): on a page with several zones the
   fill says which one the drop goes to, and the insertion line inside says where in its text. */
.editor::before,
.editor::after {
  content: '';
  position: absolute;
  inset: 0;
  border-radius: inherit;
  opacity: 0;
  pointer-events: none;
}

.editor::before {
  background: var(--accent-soft);
  transition: opacity 350ms cubic-bezier(0.15, 1, 0.3, 1);
}

.editor::after {
  border: 1px dashed var(--accent);
  transition: opacity 150ms ease;
}

.editor--plain::before,
.editor--plain::after {
  border-radius: var(--radius-sm);
}

.editor--file-target::after,
.editor--file-over::before {
  opacity: 1;
}

/* A field that takes no files: the cursor already says "no", and a line promising a place in the
   text would contradict it. Text dragged in still gets its line — this is for files only. */
.editor--file-refused .editor__body :deep(.editor__dropcursor) {
  display: none;
}

@media (prefers-reduced-motion: reduce) {
  .editor::before,
  .editor::after { transition: none; }
}

/* ── Insertion line ──────────────────────────────────────── */

/* The insertion line is just a line: thin, solid, accent-coloured. No glow, no shadows, no
   rounding, no end caps. Thickness comes from the extension's `width` option, colour from this
   class. Position animates smoothly so the line glides between gaps rather than teleporting. */
.editor__body :deep(.editor__dropcursor) {
  background-color: rgb(var(--v-theme-primary));
  border-radius: 0;
  transition:
    top 120ms ease,
    left 120ms ease,
    width 120ms ease;
}

/* Between blocks the line is horizontal, across the text column. Inside a line of text — where a
   dropped file lands — it is the plugin's own caret, 2 px wide and a line tall: stretched across
   the column like the block line, it read as a bar painted over the line it points into. */
.editor__body :deep(.editor__dropcursor.prosemirror-dropcursor-block) {
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
}

@media (prefers-reduced-motion: reduce) {
  .editor__body :deep(.editor__dropcursor) { transition-duration: 1ms; }
}

/* ── Source during a drag ────────────────────────────────── */

/* Dimmed but kept in place, on the task list's placeholder tint: it shows where the thing was
   taken from and where it returns if no drop target is chosen. Removing the block from the flow
   during a drag is not allowed — the list would collapse, the neighbours would jump, and the point
   of reference would be lost.
   The `.is-dragging` condition guards against a stuck class: without a drag there is nothing to
   dim. */
.editor.is-dragging .editor__body :deep(.is-drag-source) {
  opacity: var(--editor-drag-source-opacity);
  background: var(--editor-drag-source-bg);
  border-radius: var(--editor-drop-slot-radius);
}

/* The place the block will land, tinted — the task list's placeholder (dropSlot.ts). Its height is
   the dragged blocks' own, set inline, up to a cap: a code listing or a long table opened a gap a
   screen tall, and the document lurched under the hand on every boundary the pointer crossed. */
.editor__body :deep(.editor__drop-slot) {
  margin: 0.75em 0;
  max-height: var(--editor-drop-slot-max-height);
  background: var(--editor-drop-slot-bg);
  border-radius: var(--editor-drop-slot-radius);
  pointer-events: none;
}

/* During a block drag the slot is the indicator; the drop line stays for drags from outside. */
.editor.is-dragging .editor__body :deep(.editor__dropcursor) {
  display: none;
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
  border: 1px solid var(--editor-drag-preview-border);
  border-radius: var(--editor-drag-preview-radius);
  /* The card's padding is not part of the inner document's width: the width is carried by the
     `preview-doc` layer and must not be altered by padding — line breaks depend on it. */
  padding: 14px 18px;
  width: fit-content;
  /* Neither width nor height is clipped: a clipped card lies about what is moving. */
  /* "Picked up", the task card's lift. Set explicitly: Vuetify's elevation utilities do not make
     it into this build. */
  box-shadow: var(--editor-drag-preview-shadow);
  cursor: grabbing;
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

/* ── A picture being dragged ─────────────────────────────── */

/* The picture stays where it was, faded as a block's source is: where it was taken from and where
   it returns if let go nowhere. Its copy button keeps quiet — the pointer crossing pictures is
   aiming, not asking for a code. */
.editor.is-picture-dragging .editor__body :deep(.md-image--drag-source) {
  opacity: var(--editor-drag-source-opacity);
}

.editor.is-picture-dragging .editor__body :deep(.md-image__copy) {
  opacity: 0;
}

/* The card under the pointer is the picture itself, scaled down (`pictureDrag.ts`), lifted by the
   block preview's shadow. In the editing zone's tree, as that preview is; `fixed` so the editor
   card's `overflow: hidden` does not clip it. The card alone is rounded and clips the picture: a
   radius on the picture inside it would be a second arc, and light pixels show at the corners. */
.editor__body :deep(.md-image-drag-preview) {
  position: fixed;
  top: 0;
  left: 0;
  z-index: 3000;
  overflow: hidden;
  border-radius: var(--editor-drag-preview-radius);
  background: var(--surface);
  box-shadow: var(--editor-drag-preview-shadow);
  pointer-events: none;
}

.editor__body :deep(.md-image-drag-preview > img) {
  display: block;
  width: 100%;
  height: 100%;
  object-fit: cover;
}

/* Where it lands: the insertion line, 2 px in the block line's colour. Upright between two pictures
   (as tall as they are) and in a line of text (a caret tall); lying across a block between two blocks,
   where the picture opens a line of its own. Its box is set by the gesture; it glides between places
   like the block line. */
.editor__body :deep(.md-image-drop-line) {
  position: fixed;
  top: 0;
  left: 0;
  z-index: 3000;
  background-color: rgb(var(--v-theme-primary));
  pointer-events: none;
  visibility: hidden;
  transition:
    transform 120ms ease,
    width 120ms ease,
    height 120ms ease;
}

@media (prefers-reduced-motion: reduce) {
  .editor__body :deep(.md-image-drop-line) { transition-duration: 1ms; }
}

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

/* Inside someone else's card the counter lines up with the card's right edge, where the text column
   ends, and keeps about the same distance from the card's bottom edge as from its right one (the
   card's 16px padding). That takes a narrow strip under the text — only in a field that has a
   counter at all — with the counter reaching down into the card's padding. */
.editor--plain.editor--limited .editor__body {
  padding-bottom: 12px;
}

.editor--plain .editor__limit {
  right: 0;
  bottom: -4px;
}

/* An upload in flight, where its code will stand: a quiet chip in the line, not a block — the text
   around it does not move until the code arrives. ProseMirror draws the widget, hence `:deep`. */
.editor__body :deep(.editor__attaching) {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  margin: 0 2px;
  padding: 0 8px;
  border-radius: var(--radius-sm);
  background: var(--accent-soft);
  color: var(--text-muted);
  font-size: 12px;
  line-height: 20px;
  vertical-align: baseline;
  user-select: none;
}

.editor__body :deep(.editor__attaching)::before {
  content: '';
  width: 10px;
  height: 10px;
  border: 2px solid currentColor;
  border-right-color: transparent;
  border-radius: 50%;
  animation: editor-attaching 0.8s linear infinite;
}

@keyframes editor-attaching {
  to { transform: rotate(360deg); }
}

@media (prefers-reduced-motion: reduce) {
  .editor__body :deep(.editor__attaching)::before { animation: none; }
}

/* Yellow — "the limit is near", red — "you'll hit it in a couple of words", and red as well for a
   body that arrived over the limit. Theme colours, as in `LimitField`: in the light theme warning
   is a dark amber, pure yellow on white would not be readable. */
.editor__limit.is-warning {
  color: rgb(var(--v-theme-warning));
  font-weight: 500;
}

.editor__limit.is-danger {
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

<!-- Not `scoped`: while a picture is held the pointer leaves the field, and the gesture's cursor and
     its stop on text selection go on `body` (`pictureDrag.ts`). In a scoped block `body.x *` would
     compile to a bare `body.x` and lose the rest of itself. -->
<style>
body.md-picture-dragging,
body.md-picture-dragging * {
  cursor: grabbing !important;
  user-select: none !important;
}
</style>
