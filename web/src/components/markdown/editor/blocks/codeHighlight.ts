// Highlighting of editable code blocks as ProseMirror decorations.
//
// The text stays the document's own: the caret, selection, undo and paste work on it as on any
// text, and the colour is laid over it as inline decorations — spans ProseMirror owns and redraws.
// Each span carries both palettes (`--shiki-light` / `--shiki-dark`), the CSS of the block picks
// one, so a theme switch costs nothing here.
//
// Per keystroke the set is rebuilt, never patched: `DecorationSet.remove` / `add` on a block of
// thousands of tokens cost seconds (measured on `/design-system/code-editor-lab`). Untouched blocks
// take their decorations from the
// previous set mapped through the transaction; a touched block is re-tokenized at once if it is
// small, and if it is large keeps its mapped colours until typing pauses — tokenizing a thousand
// lines takes ~300 ms, which a keystroke cannot afford.
import { Plugin, PluginKey, type EditorState, type Transaction } from '@tiptap/pm/state'
import { Decoration, DecorationSet } from '@tiptap/pm/view'
import type { Node as PMNode } from '@tiptap/pm/model'
import { onLanguageReady, tokensFor } from '@/composables/useHighlighter'

export interface HighlightStats {
  /** Duration of the last pass, ms. */
  lastMs: number
  /** The slowest pass since load, ms. */
  maxMs: number
  /** Blocks re-tokenized by the last pass. */
  blocks: number
  /** Decorations in the document after the last pass. */
  decorations: number
  full: boolean
  /** Blocks waiting for a pause in typing. */
  deferred: number
}

interface HighlightState {
  set: DecorationSet
  /** Start positions of large blocks edited since their last tokenization. */
  stale: number[]
}

export const highlightKey = new PluginKey<HighlightState>('codeHighlight')

/** Token class; the code block view's CSS paints it from the two palettes. */
export const TOKEN_CLASS = 'code-token'

const REFRESH = 'refresh'
const SETTLE = 'settle'
/** Above this many characters a block is re-tokenized after a pause, not on the keystroke. */
const SYNC_LIMIT = 3000
const PAUSE_MS = 250

function blockDecorations(node: PMNode, pos: number): Decoration[] {
  const tokens = tokensFor(node.textContent, String(node.attrs.language ?? ''))
  if (!tokens) return []
  const start = pos + 1
  return tokens.map((token) =>
    Decoration.inline(start + token.offset, start + token.offset + token.length, {
      class: TOKEN_CLASS,
      style: token.style,
    }),
  )
}

function touchedBlocks(tr: Transaction): Set<number> {
  const touched = new Set<number>()
  tr.mapping.maps.forEach((map, index) => {
    const rest = tr.mapping.slice(index + 1)
    map.forEach((_oldStart, _oldEnd, newStart, newEnd) => {
      const from = Math.max(0, rest.map(newStart, -1))
      const to = Math.min(tr.doc.content.size, rest.map(newEnd, 1))
      tr.doc.nodesBetween(from, to, (node, pos) => {
        if (node.type.name !== 'codeBlock') return true
        touched.add(pos)
        return false
      })
    })
  })
  return touched
}

interface Pass {
  state: HighlightState
  blocks: number
}

/**
 * One walk over the code blocks. `retokenize` says which blocks get fresh tokens; every other
 * block keeps what `kept` holds for its range.
 */
function pass(doc: PMNode, kept: DecorationSet | null, retokenize: (node: PMNode, pos: number) => boolean, stale: number[]): Pass {
  const decorations: Decoration[] = []
  let blocks = 0
  doc.descendants((node, pos) => {
    if (node.type.name !== 'codeBlock') return true
    if (!kept || retokenize(node, pos)) {
      blocks++
      decorations.push(...blockDecorations(node, pos))
    } else {
      decorations.push(...kept.find(pos, pos + node.nodeSize))
    }
    return false
  })
  return { state: { set: DecorationSet.create(doc, decorations), stale }, blocks }
}

function fullPass(doc: PMNode): Pass {
  return pass(doc, null, () => true, [])
}

function editPass(tr: Transaction, previous: HighlightState): Pass {
  const mapped = previous.set.map(tr.mapping, tr.doc)
  const stale = previous.stale.map((pos) => tr.mapping.map(pos))
  const touched = touchedBlocks(tr)
  if (!touched.size) return { state: { set: mapped, stale }, blocks: 0 }
  return pass(tr.doc, mapped, (node, pos) => {
    if (!touched.has(pos)) return false
    if (node.textContent.length <= SYNC_LIMIT) return true
    if (!stale.includes(pos)) stale.push(pos)
    return false
  }, stale)
}

function settlePass(doc: PMNode, previous: HighlightState): Pass {
  const waiting = new Set(previous.stale)
  return pass(doc, previous.set, (_node, pos) => waiting.has(pos), [])
}

export function codeHighlight(onStats?: (stats: HighlightStats) => void): Plugin {
  let maxMs = 0

  function measure(full: boolean, run: () => Pass): HighlightState {
    const started = performance.now()
    const { state, blocks } = run()
    const lastMs = performance.now() - started
    maxMs = Math.max(maxMs, lastMs)
    onStats?.({ lastMs, maxMs, blocks, decorations: state.set.find().length, full, deferred: state.stale.length })
    return state
  }

  return new Plugin<HighlightState>({
    key: highlightKey,
    state: {
      init: (_config, state: EditorState) => measure(true, () => fullPass(state.doc)),
      apply(tr, previous) {
        const meta = tr.getMeta(highlightKey)
        if (meta === REFRESH) return measure(true, () => fullPass(tr.doc))
        if (meta === SETTLE) return measure(false, () => settlePass(tr.doc, previous))
        if (!tr.docChanged) return previous
        return measure(false, () => editPass(tr, previous))
      },
    },
    props: {
      decorations: (state) => highlightKey.getState(state)?.set,
    },
    view(view) {
      let timer: ReturnType<typeof setTimeout> | null = null
      const stop = onLanguageReady(() => {
        if (!view.isDestroyed) view.dispatch(view.state.tr.setMeta(highlightKey, REFRESH))
      })
      return {
        // Every edit restarts the wait: the large block is tokenized once typing pauses.
        update(current, previousState) {
          if (current.state.doc === previousState.doc) return
          if (timer) clearTimeout(timer)
          timer = null
          if (!highlightKey.getState(current.state)?.stale.length) return
          timer = setTimeout(() => {
            timer = null
            if (!view.isDestroyed) view.dispatch(view.state.tr.setMeta(highlightKey, SETTLE))
          }, PAUSE_MS)
        },
        destroy() {
          if (timer) clearTimeout(timer)
          stop()
        },
      }
    },
  })
}
