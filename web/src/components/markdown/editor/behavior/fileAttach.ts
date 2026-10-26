// Files pasted or dropped into a field become files of the field's holder, and their codes stand in
// the text where they were put.
//
// What a holder is, where a file goes and which code it gets is the page's to know, not the
// editor's: the page hands the field one function, `attach(file)`, that uploads a file and answers
// with the text the file stands for in the body. Without it a paste and a drop are what they always
// were (`markdownPaste.ts`).
//
// The upload takes time, and the document does not wait for it. A placeholder — a widget, no
// content — marks the spot; every transaction maps it on, so text typed or deleted around it does
// not move it onto someone else's words. The files of one paste or drop go one at a time, in their
// order. When the last has answered, the placeholder goes and the codes of those that made it go in
// at once, in ONE transaction, a blank between each (pictures in a row are a gallery): a code is
// either in the text whole or not at all. A file that failed is reported and left out; when none
// made it, nothing is written. A paste over a selection keeps the selection until then: the codes
// replace it, and a paste whose files all failed leaves the text as it was.
//
// The codes go into the document the paste happened in, or nowhere. A placeholder is cancelled when
// that document is gone — the field loaded a value from outside (another task opened in the same
// page, the agent or another tab changed the field: `DOCUMENT_REPLACED`, or any step replacing the
// whole document), the field's holder changed (`attach` is another function), the editor was
// destroyed. The files stay attached — they are in the holder's list — and the person is told that
// their codes were not put into the text.
//
// The codes are parsed the way the field parses any text (`contentFor`), so a picture is a picture
// and a pill a pill the moment they land. The length limit (`lengthLimit.ts`) still has the last
// word: a body with no room for the codes refuses the insertion whole, and the field says so.
//
// Before anything is sent, what cannot go is set aside and said: a folder (`shared/utils/fileDrop.ts`
// tells it apart) and a file the page refuses up front (`refuse`: over the size ceiling). The rest
// go; with nothing left, no placeholder appears at all. A drop that brings only the files' addresses
// on the disk is the editor's own business (`MarkdownEditor.vue`, every field, ahead of this one).
// Files picked in a dialog — the slash command — come in by `attachFiles` and land at the caret, the
// way a paste does.
import { Extension } from '@tiptap/core'
import { Fragment, type Node as PMNode } from '@tiptap/pm/model'
import { Plugin, PluginKey, TextSelection, type EditorState, type Transaction } from '@tiptap/pm/state'
import { Decoration, DecorationSet, type EditorView } from '@tiptap/pm/view'

import { settleDropped, sortDropped, sortFiles, type SortedDrop } from '@/shared/utils/fileDrop'

/** Upload one file into the field's holder; resolves with the text it stands for in the body. */
export type AttachFile = (file: File) => Promise<string>

/** A file the holder will not take, known before sending: the reason; `null` — send it. */
export type RefuseFile = (file: File) => string | null

declare module '@tiptap/core' {
  interface Commands<ReturnType> {
    fileAttach: {
      attachFiles: (files: File[]) => ReturnType
    }
  }
}

// ── What a paste or a drop carries ────────────────────────────────────────────

// A picture an app put on the clipboard as markup rather than as a file.
const DATA_IMAGE = /<img\b[^>]*?\bsrc\s*=\s*["'](data:image\/([a-z0-9.+-]+);base64,([a-z0-9+/=\s]+))["']/gi

const EXTENSIONS: Record<string, string> = { jpeg: 'jpg', 'svg+xml': 'svg' }

/** The `data:` pictures of a piece of HTML, as files named `image-1.png`, `image-2.jpg`… */
export function dataImageFiles(html: string): File[] {
  const files: File[] = []
  for (const match of html.matchAll(DATA_IMAGE)) {
    const subtype = match[2].toLowerCase()
    let bytes: Uint8Array<ArrayBuffer>
    try {
      const binary = atob(match[3].replace(/\s+/g, ''))
      bytes = Uint8Array.from(binary, (char) => char.charCodeAt(0))
    } catch {
      continue
    }
    const extension = EXTENSIONS[subtype] ?? subtype
    files.push(new File([bytes], `image-${files.length + 1}.${extension}`, { type: `image/${subtype}` }))
  }
  return files
}

/** The clipboard's shape, as much of a `DataTransfer` as the choice needs. */
export interface ClipboardLike {
  files: ArrayLike<File>
  getData(format: string): string
}

/**
 * The files a paste brings, or none — then it is a paste of text.
 *
 * A screenshot, a picture a browser copied, a file copied in a file manager — files, maybe with a
 * name or an `<img>` beside them. Text that came with its markup (a selection in a browser, cells
 * of a table, which also put a picture of themselves on the clipboard) is a paste of text. With no
 * file and no text, the `data:` pictures of the markup are the files.
 *
 * A picture with no name of its own is renamed by the moment of the paste (`timeNamed`); a file
 * with its own name — a PDF or a photo copied in a file manager — keeps it.
 */
export function pastedFiles(data: ClipboardLike | null | undefined, now = new Date()): File[] {
  if (!data) return []
  const plain = data.getData('text/plain').trim()
  const html = data.getData('text/html')
  const files = Array.from(data.files)
  if (files.length) return plain && html ? [] : timeNamed(files, now)
  if (plain || !html) return []
  return timeNamed(dataImageFiles(html), now, () => true)
}

// The name a browser gives a picture that has none. A file truly named `image.png` and copied in a
// file manager comes the same way, and the browser gives no means to tell the two apart.
const UNNAMED_PICTURE = /^image\.[a-z0-9]+$/i

const hasNoName = (file: File) => file.type.startsWith('image/') && UNNAMED_PICTURE.test(file.name)

/**
 * The unnamed pictures among `files` named `screenshot-2026-10-26-14-03-22.png` by the local time
 * of `now` — five screenshots under one `image.png` would be five lines alike in the holder's
 * list. Several in one paste are numbered (`…-22-1.png`, `…-22-2.png`); the rest stay as they are.
 * `unnamed` — which files have no name of their own; the pictures of markup have none at all.
 */
export function timeNamed(files: File[], now: Date, unnamed: (file: File) => boolean = hasNoName): File[] {
  const nameless = files.filter(unnamed)
  if (!nameless.length) return files
  const stamp = localStamp(now)
  return files.map((file) => {
    const index = nameless.indexOf(file)
    if (index < 0) return file
    const number = nameless.length > 1 ? `-${index + 1}` : ''
    const extension = file.name.slice(file.name.lastIndexOf('.'))
    return new File([file], `screenshot-${stamp}${number}${extension}`, {
      type: file.type,
      lastModified: file.lastModified,
    })
  })
}

function localStamp(moment: Date): string {
  const two = (value: number) => String(value).padStart(2, '0')
  const date = `${moment.getFullYear()}-${two(moment.getMonth() + 1)}-${two(moment.getDate())}`
  return `${date}-${two(moment.getHours())}-${two(moment.getMinutes())}-${two(moment.getSeconds())}`
}

// ── What goes into the text ───────────────────────────────────────────────────

const BLANK = /\s/

/**
 * The text that goes in for the files that made it: their texts a blank apart, with a blank on
 * either side where the neighbouring character is not one — a code glued to a word reads as part
 * of it. `before` / `after` — the characters next to the spot (`''` at the edge of a paragraph).
 */
export function insertionText(texts: readonly string[], before: string, after: string): string {
  const { lead, body, tail } = insertionParts(texts, before, after)
  return lead + body + tail
}

/**
 * The same text in three parts: the blanks at the edges go in as plain text, the body is parsed —
 * markdown drops the blanks at a paragraph's edges, and a code would end up glued to the word
 * after all.
 */
export function insertionParts(
  texts: readonly string[],
  before: string,
  after: string,
): { lead: string; body: string; tail: string } {
  const body = texts.filter(Boolean).join(' ')
  if (!body) return { lead: '', body: '', tail: '' }
  return {
    lead: before !== '' && !BLANK.test(before) ? ' ' : '',
    body,
    tail: after !== '' && !BLANK.test(after) ? ' ' : '',
  }
}

// An atom (a pill, a picture) counts as a character: two codes side by side are still two words.
const LEAF = '￼'

/** The characters either side of `pos` inside its paragraph; `''` at an edge. */
export function textAround(doc: PMNode, pos: number): { before: string; after: string } {
  const $pos = doc.resolve(pos)
  const start = $pos.start()
  const end = $pos.end()
  return {
    before: pos > start ? doc.textBetween(pos - 1, pos, '', LEAF) : '',
    after: pos < end ? doc.textBetween(pos, pos + 1, '', LEAF) : '',
  }
}

// ── The placeholder ───────────────────────────────────────────────────────────

interface Spot {
  id: number
  /** Where the codes go; with `end` past it, the selection the paste replaces. */
  pos: number
  end: number
  render: () => HTMLElement
}

export const FILE_ATTACH_KEY = new PluginKey<readonly Spot[]>('fileAttach')

/**
 * Transaction meta: the document was loaded from outside (the field's value changed under it). The
 * text a placeholder stood in is gone, and every pending insertion is cancelled.
 */
export const DOCUMENT_REPLACED = 'fileAttachDocumentReplaced'

type PlaceholderMeta = { add: Spot } | { remove: number }

/** A step replaced everything the document held — whatever the edit was, it is another text now. */
function replacesWholeDocument(tr: Transaction): boolean {
  return tr.steps.some((step, index) => {
    const { from, to } = step as unknown as { from?: number; to?: number }
    return from === 0 && to === tr.docs[index].content.size && to > 0
  })
}

function mapSpot(spot: Spot, tr: Transaction): Spot {
  // An empty spot maps to the left: text typed at it goes after it, so the codes land where the
  // file was put and the typing carries on behind them. A selection keeps typing at its edges out.
  if (spot.pos === spot.end) {
    const pos = tr.mapping.map(spot.pos, -1)
    return { ...spot, pos, end: pos }
  }
  const pos = tr.mapping.map(spot.pos, 1)
  return { ...spot, pos, end: Math.max(pos, tr.mapping.map(spot.end, -1)) }
}

// The spots are kept as positions, not as decorations: a decoration set drops a widget whose text
// was deleted around it, and the upload would then have nowhere to land. A position mapped
// through a deletion lands at its edge — the codes still go in, whole. A whole new document is not
// a deletion around the spot, and cancels it.
/** Where uploads in flight wait: positions mapped through every change, drawn as widgets. */
export function placeholderPlugin(): Plugin<readonly Spot[]> {
  return new Plugin<readonly Spot[]>({
    key: FILE_ATTACH_KEY,
    state: {
      init: () => [],
      apply(tr, spots) {
        let next = spots
        if (tr.getMeta(DOCUMENT_REPLACED) || (tr.docChanged && replacesWholeDocument(tr))) next = []
        else if (tr.docChanged) next = spots.map((spot) => mapSpot(spot, tr))
        const meta = tr.getMeta(FILE_ATTACH_KEY) as PlaceholderMeta | undefined
        if (meta && 'add' in meta) next = [...next, meta.add]
        else if (meta && 'remove' in meta) next = next.filter((spot) => spot.id !== meta.remove)
        return next
      },
    },
    props: {
      decorations(state) {
        const spots = FILE_ATTACH_KEY.getState(state) ?? []
        if (!spots.length) return DecorationSet.empty
        return DecorationSet.create(state.doc, spots.map(({ id, pos, render }) =>
          Decoration.widget(pos, render, { id, side: -1, ignoreSelection: true, key: `file-attach-${id}` })))
      },
    },
  })
}

/** Put a placeholder at `pos` in `tr`; `end` past it — the range the codes will replace. */
export function addPlaceholder(
  tr: Transaction,
  id: number,
  pos: number,
  render: () => HTMLElement,
  end: number = pos,
): Transaction {
  return tr.setMeta(FILE_ATTACH_KEY, { add: { id, pos, end, render } } satisfies PlaceholderMeta)
}

/**
 * A placeholder over the selection, the document untouched: a paste replaces the selection only
 * when its codes arrive, so a paste whose files all fail leaves the text as it was.
 */
export function placeholderAtSelection(state: EditorState, id: number, render: () => HTMLElement): Transaction {
  const { from, to } = state.selection
  return addPlaceholder(state.tr, id, from, render, to)
}

function spotOf(state: EditorState, id: number): Spot | null {
  return FILE_ATTACH_KEY.getState(state)?.find((spot) => spot.id === id) ?? null
}

/** Where the placeholder stands now; `null` — it is gone. */
export function placeholderPos(state: EditorState, id: number): number | null {
  return spotOf(state, id)?.pos ?? null
}

/** The transaction that takes the placeholder away and writes nothing. */
export function dropPlaceholder(state: EditorState, id: number): Transaction {
  return state.tr.setMeta(FILE_ATTACH_KEY, { remove: id } satisfies PlaceholderMeta)
}

/** Inline content for a piece of text, parsed the way the field parses it. */
export type ContentFor = (text: string, state: EditorState) => Fragment | null

/**
 * The transaction that takes the placeholder away and puts the texts in its place — over the
 * selection it was made on, if any; `null` — the placeholder is gone (cancelled). With no texts it
 * only takes the placeholder away, and the selection stays as it was.
 */
export function settlePlaceholder(
  state: EditorState,
  id: number,
  texts: readonly string[],
  contentFor: ContentFor,
): Transaction | null {
  const spot = spotOf(state, id)
  if (spot === null) return null
  const { pos, end } = spot
  const tr = dropPlaceholder(state, id)
  const { before } = textAround(state.doc, pos)
  const { after } = textAround(state.doc, end)
  const { lead, body, tail } = insertionParts(texts, before, after)
  if (!body) return tr
  const text = lead + body + tail

  const caretHere = state.selection.from === pos && state.selection.to === end
  const $pos = state.doc.resolve(pos)
  const parsed = $pos.parent.type.spec.code ? null : contentFor(body, state)
  let size = text.length
  try {
    if (!parsed) throw new Error('as text')
    let content = parsed
    if (lead) content = Fragment.from(state.schema.text(lead)).append(content)
    if (tail) content = content.append(Fragment.from(state.schema.text(tail)))
    tr.replaceWith(pos, end, content)
    size = content.size
  } catch {
    tr.insertText(text, pos, end)
  }
  // The person who pasted and waited carries on after the codes, not before them.
  if (caretHere) tr.setSelection(TextSelection.create(tr.doc, pos + size))
  return tr
}

// ── The extension ─────────────────────────────────────────────────────────────

export interface FileAttachOptions {
  /** The page's upload; unset — files are not taken here. Read at the moment of use. */
  attach: () => AttachFile | undefined
  /** The page's refusal before sending; unset — every file is sent. Read at the moment of use. */
  refuse: () => RefuseFile | undefined
  contentFor: ContentFor
  /** The placeholder's words while the `done`-th of `total` files goes. */
  label: (done: number, total: number) => string
  /** A file did not make it — the reason, as the upload gave it. */
  onFailure: (error: unknown) => void
  /** A file was not sent — the page's reason (`refuse`). */
  onRefused: (reason: string) => void
  /** Folders were among the files and were not sent — their names. */
  onFolders: (names: string[]) => void
  /** The codes were ready and the field had no room for them. */
  onNoRoom: () => void
  /** The codes were ready and the text they belonged to is gone: another value, another holder. */
  onNotInserted: () => void
}

let nextId = 0

function placeholder(label: string): { element: HTMLElement; render: () => HTMLElement } {
  const element = document.createElement('span')
  element.className = 'editor__attaching'
  element.setAttribute('contenteditable', 'false')
  element.setAttribute('role', 'status')
  element.textContent = label
  return { element, render: () => element }
}

/** The files that may go: folders and the page's refusals are said and left out. */
export function sendable(
  files: readonly File[],
  folders: readonly string[],
  refuse: RefuseFile | undefined,
  report: Pick<FileAttachOptions, 'onFolders' | 'onRefused'>,
): File[] {
  if (folders.length) report.onFolders([...folders])
  const kept: File[] = []
  for (const file of files) {
    const reason = refuse?.(file) ?? null
    if (reason) report.onRefused(reason)
    else kept.push(file)
  }
  return kept
}

async function attachAll(
  view: EditorView,
  begin: (id: number, render: () => HTMLElement) => Transaction,
  sorted: SortedDrop,
  attach: AttachFile,
  options: FileAttachOptions,
): Promise<void> {
  // Known at once in nearly every case: then a drop with nothing to send leaves no trace at all.
  // A file the browser said nothing about is read first, behind the placeholder.
  let files = sorted.unsure.length ? null : sendable(sorted.files, sorted.folders, options.refuse(), options)
  if (files && !files.length) return

  const id = nextId++
  const mark = placeholder(options.label(1, files?.length ?? 1))
  view.dispatch(begin(id, mark.render))

  if (!files) {
    const settled = await settleDropped(sorted)
    files = sendable(settled.files, settled.folders, options.refuse(), options)
    if (!files.length) {
      if (!view.isDestroyed) view.dispatch(dropPlaceholder(view.state, id))
      return
    }
  }

  const texts: string[] = []
  for (const [index, file] of files.entries()) {
    mark.element.textContent = options.label(index + 1, files.length)
    try {
      texts.push(await attach(file))
    } catch (error) {
      options.onFailure(error)
    }
  }
  const made = texts.some(Boolean)
  if (view.isDestroyed) {
    if (made) options.onNotInserted()
    return
  }
  // The field now edits another holder's text: the codes belong to the one the files went to.
  if (options.attach() !== attach) {
    view.dispatch(dropPlaceholder(view.state, id))
    if (made) options.onNotInserted()
    return
  }

  const tr = settlePlaceholder(view.state, id, texts, options.contentFor)
  if (!tr) {
    if (made) options.onNotInserted()
    return
  }
  view.dispatch(tr)
  if (placeholderPos(view.state, id) !== null) {
    // The length limit refused the whole transaction: the placeholder goes on its own.
    view.dispatch(dropPlaceholder(view.state, id))
    options.onNoRoom()
  }
}

export const FileAttach = Extension.create<FileAttachOptions>({
  name: 'fileAttach',

  addOptions() {
    return {
      attach: () => undefined,
      refuse: () => undefined,
      contentFor: () => null,
      label: () => '',
      onFailure: () => {},
      onRefused: () => {},
      onFolders: () => {},
      onNoRoom: () => {},
      onNotInserted: () => {},
    }
  },

  addCommands() {
    const options = this.options
    return {
      // Files picked in a dialog: they land at the caret, over the selection, as a paste does.
      attachFiles: (files: File[]) => ({ view }) => {
        const attach = options.attach()
        if (!attach || !view.editable || !files.length) return false
        void attachAll(view, (id, render) => placeholderAtSelection(view.state, id, render), sortFiles(files), attach, options)
        return true
      },
    }
  },

  addProseMirrorPlugins() {
    const options = this.options
    return [
      placeholderPlugin(),
      new Plugin({
        props: {
          handlePaste(view, event) {
            const attach = options.attach()
            if (!attach || !view.editable) return false
            const files = pastedFiles(event.clipboardData)
            if (!files.length) return false
            event.preventDefault()
            void attachAll(view, (id, render) => placeholderAtSelection(view.state, id, render), sortFiles(files), attach, options)
            return true
          },
          handleDrop(view, event, _slice, moved) {
            const attach = options.attach()
            if (moved || !attach || !view.editable) return false
            // The folders are told apart now: the drop's items are gone once the handler returns.
            const sorted = sortDropped(event.dataTransfer)
            if (!sorted.files.length && !sorted.folders.length) return false
            event.preventDefault()
            const at = view.posAtCoords({ left: event.clientX, top: event.clientY })
            // A drop is an edit of this field: it takes the focus, as a paste has it already, so a
            // field that saves when it is left saves the codes too.
            view.focus()
            const pos = at?.pos ?? view.state.selection.from
            void attachAll(view, (id, render) => addPlaceholder(view.state.tr, id, pos, render), sorted, attach, options)
            return true
          },
        },
      }),
    ]
  },
})
