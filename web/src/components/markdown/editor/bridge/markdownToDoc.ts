// Markdown → flat document: the parsing half of the bridge.
//
// Tokens come from markdown-it — the same one that renders bodies — so a construct the renderer
// understands is understood by the editor too, and the definition of an entity code (REF_CODE)
// stays single for the whole app. The markdown-it tree is flattened here into a row of blocks by
// the schema's rules (blocks.ts): a nested list becomes an item with a larger `depth`, a quote
// paragraph becomes a `quote` block.
//
// The printing half lives in docToMarkdown.ts; neither can be trusted alone, so the design-system
// page runs them against each other and shows any divergence.
import MarkdownIt from 'markdown-it'
import type { Token } from 'markdown-it'
import type { JSONContent } from '@tiptap/core'
import { canonicalCode, REF_CODE, TASK_MARKER, WHOLE_CODE_SPAN } from '../../shared/contracts'
import type { FeatureSet } from '../modes'
import { restrict } from './restrict'

// What counts as an entity code, what counts as a whole code in backticks and what a checklist
// marker looks like is decided by `markdown/shared/contracts` — one file for the renderer and the
// editor. Were they to diverge, a pill would change meaning on entering edit mode.

// `breaks: false` — a single newline inside a paragraph is insignificant in a body, so it arrives
// as a space, and the paragraph is re-wrapped on output. The only normalization the bridge makes
// deliberately.
const md = new MarkdownIt({ html: false, linkify: true, breaks: false })
md.linkify.set({ fuzzyLink: false, fuzzyEmail: false })

type Mark = { type: string; attrs?: Record<string, unknown> }

/**
 * @param features the field's feature set; when omitted, parse everything we can. Parsing is
 *   always full, and narrowing is a separate pass (`restrict`): that way the filter reads as one
 *   piece instead of being scattered across twenty branches of the main loop.
 */
export function markdownToDoc(markdown: string, features?: FeatureSet): JSONContent {
  const doc = parseFull(markdown)
  return features ? restrict(doc, features) : doc
}

function parseFull(markdown: string): JSONContent {
  const tokens = md.parse(markdown, {})
  const doc: JSONContent = { type: 'doc', content: [] }
  // The stack holds only the open text block: blocks do not nest, so it never gets deeper than
  // two levels.
  const stack: JSONContent[] = [doc]
  const ordered: boolean[] = []
  let list: JSONContent | null = null
  let listDepth = 0
  let quoteDepth = 0

  const top = (): JSONContent => stack[stack.length - 1]
  const inItem = (): boolean => top().type === 'listItem'
  const open = (node: JSONContent): void => {
    ;(doc.content ??= []).push(node)
    stack.push(node)
  }
  // A top-level block that ends up inside a list item (code in an item, a nested quote) does not
  // fit the flat schema and is dropped — see UNSUPPORTED.
  const addBlock = (node: JSONContent): void => {
    if (!inItem()) (doc.content ??= []).push(node)
  }

  for (let i = 0; i < tokens.length; i += 1) {
    const token = tokens[i]

    switch (token.type) {
      // A table is parsed by a separate function that returns the index of its closing token:
      // inside it the tokens have a grammar of their own, and mixing it into the flat block
      // parse would mean tracking four extra states in the main loop.
      case 'table_open': {
        const parsed = parseTable(tokens, i)
        if (parsed.node) addBlock(parsed.node)
        i = parsed.end
        break
      }

      case 'heading_open':
        open({ type: 'heading', attrs: { level: Number(token.tag.slice(1)) }, content: [] })
        break

      case 'paragraph_open':
        // There is no paragraph inside an item: the item holds inline content directly.
        if (inItem()) break
        open({ type: quoteDepth > 0 ? 'quote' : 'paragraph', content: [] })
        break

      case 'paragraph_close':
        if (inItem()) break
        stack.pop()
        break

      case 'heading_close':
        stack.pop()
        break

      // A quote is not a container but a block flag: only the depth is counted, to know which
      // type to open paragraphs inside it with.
      case 'blockquote_open':
        quoteDepth += 1
        break
      case 'blockquote_close':
        quoteDepth -= 1
        break

      case 'bullet_list_open':
      case 'ordered_list_open':
        if (listDepth === 0) {
          list = { type: 'list', content: [] }
          ;(doc.content ??= []).push(list)
        }
        ordered[listDepth] = token.type === 'ordered_list_open'
        listDepth += 1
        break

      case 'bullet_list_close':
      case 'ordered_list_close':
        listDepth -= 1
        if (listDepth === 0) list = null
        break

      case 'list_item_open': {
        if (!list) break
        const task = taskAt(tokens, i)
        const item: JSONContent = {
          type: 'listItem',
          attrs: {
            // Markdown nesting becomes a number: the list level minus one.
            depth: Math.max(0, listDepth - 1),
            ordered: ordered[listDepth - 1] ?? false,
            checked: task ? task.checked : null,
          },
          content: [],
        }
        ;(list.content ??= []).push(item)
        stack.push(item)
        break
      }

      case 'list_item_close':
        if (inItem()) stack.pop()
        break

      case 'inline':
        ;(top().content ??= []).push(...inlineContent(token.children ?? []))
        break

      case 'fence':
      case 'code_block': {
        const code = token.content.replace(/\n$/, '')
        addBlock({
          type: 'codeBlock',
          attrs: { language: fenceLanguage(token) },
          content: code ? [{ type: 'text', text: code }] : [],
        })
        break
      }

      case 'hr':
        addBlock({ type: 'horizontalRule' })
        break

      default:
        break
    }
  }

  // ProseMirror will not accept an empty document: `doc` requires at least one block.
  if (!doc.content?.length) doc.content = [{ type: 'paragraph' }]
  return doc
}

// ── Table ─────────────────────────────────────────────────────────────────────

// markdown-it reports alignment as an inline style on the HEADER cell — where the delimiter row
// declares it. It is taken once, as one list per table: keeping a copy on every cell would mean
// syncing them on every column edit.
const ALIGN_STYLE = /text-align\s*:\s*(left|center|right)/

function alignOf(token: Token): 'left' | 'center' | 'right' | null {
  // `attrGet` is typed `string | number`: markdown-it attribute values need not be strings,
  // although `style` always arrives as one.
  const match = ALIGN_STYLE.exec(String(token.attrGet('style') ?? ''))
  return match ? (match[1] as 'left' | 'center' | 'right') : null
}

/**
 * Parses a table from `table_open` to its matching `table_close`.
 *
 * Body rows are squared to the header's width: markdown-it returns a row as written, while the
 * schema and the printer expect a rectangle. Missing cells are filled with empty ones, extra ones
 * are dropped — exactly how GFM itself reads such a row.
 */
function parseTable(tokens: Token[], start: number): { node: JSONContent | null; end: number } {
  const align: ('left' | 'center' | 'right' | null)[] = []
  const head: JSONContent[] = []
  const body: JSONContent[] = []
  let into: JSONContent[] = head
  let row: JSONContent | null = null
  let cell: JSONContent | null = null
  let i = start + 1

  for (; i < tokens.length; i += 1) {
    const token = tokens[i]
    if (token.type === 'table_close') break

    switch (token.type) {
      case 'thead_open': into = head; break
      case 'tbody_open': into = body; break

      case 'tr_open':
        row = { type: 'tableRow', content: [] }
        break
      case 'tr_close':
        if (row) into.push(row)
        row = null
        break

      case 'th_open':
      case 'td_open':
        cell = { type: 'tableCell', attrs: { header: token.type === 'th_open' }, content: [] }
        if (token.type === 'th_open') align.push(alignOf(token))
        break
      case 'th_close':
      case 'td_close':
        if (cell && row) (row.content ??= []).push(cell)
        cell = null
        break

      case 'inline':
        if (cell) (cell.content ??= []).push(...inlineContent(token.children ?? []))
        break

      default:
        break
    }
  }

  const headRow = head[0]
  // No header, no table: GFM requires it, and building the node without one would hand the
  // schema a document it rejects as a whole.
  if (!headRow) return { node: null, end: i }

  const width = (headRow.content ?? []).length
  const squared = body.map((entry) => ({
    ...entry,
    content: Array.from({ length: width }, (_, index) => (entry.content ?? [])[index]
      ?? { type: 'tableCell', attrs: { header: false }, content: [] }),
  }))

  return {
    node: {
      type: 'table',
      attrs: { align: Array.from({ length: width }, (_, index) => align[index] ?? null) },
      content: [
        { type: 'tableHead', content: [headRow] },
        { type: 'tableBody', content: squared },
      ],
    },
    end: i,
  }
}

// An item is a checklist item if its paragraph opens with `[ ]` / `[x]`. The marker is stripped
// from both the token and its first child — exactly as the renderer does it.
function taskAt(tokens: Token[], index: number): { checked: boolean } | null {
  const paragraph = tokens[index + 1]
  const inline = tokens[index + 2]
  if (paragraph?.type !== 'paragraph_open' || inline?.type !== 'inline') return null
  const marker = TASK_MARKER.exec(inline.content)
  const first = inline.children?.[0]
  if (!marker || first?.type !== 'text') return null
  inline.content = inline.content.slice(marker[0].length)
  first.content = first.content.slice(marker[0].length)
  return { checked: marker[1] !== ' ' }
}

const CODE_LANGUAGE = /^[\w+-]+$/

function fenceLanguage(token: Token): string | null {
  const info = token.info.trim().split(/\s+/)[0] ?? ''
  return CODE_LANGUAGE.test(info) ? info : null
}

function inlineContent(children: Token[]): JSONContent[] {
  const out: JSONContent[] = []
  const marks: Mark[] = []

  const drop = (type: string): void => {
    const at = marks.map((mark) => mark.type).lastIndexOf(type)
    if (at >= 0) marks.splice(at, 1)
  }

  for (const token of children) {
    switch (token.type) {
      case 'text':
        out.push(...textWithRefs(token.content, marks))
        break

      case 'code_inline': {
        const code = token.content.trim()
        if (WHOLE_CODE_SPAN.test(code)) out.push(refNode(code))
        else out.push(textNode(token.content, [...marks, { type: 'code' }]))
        break
      }

      case 'strong_open': marks.push({ type: 'bold' }); break
      case 'strong_close': drop('bold'); break
      case 'em_open': marks.push({ type: 'italic' }); break
      case 'em_close': drop('italic'); break
      case 's_open': marks.push({ type: 'strike' }); break
      case 's_close': drop('strike'); break

      case 'link_open':
        marks.push({ type: 'link', attrs: { href: token.attrGet('href') ?? '' } })
        break
      case 'link_close':
        drop('link')
        break

      case 'hardbreak':
        out.push({ type: 'hardBreak' })
        break
      case 'softbreak':
        out.push(textNode(' ', marks))
        break

      default:
        break
    }
  }

  // ProseMirror forbids empty text nodes and rejects the WHOLE document if it meets even one —
  // the editor silently stays empty. markdown-it, meanwhile, emits an empty `text` routinely: at
  // the junction of inline tokens, at the start of a line that opens with code. The filter lives
  // here rather than at each source: otherwise any new way of producing an empty node would wipe
  // the document again.
  return out.filter((node) => node.type !== 'text' || (node.text ?? '').length > 0)
}

// A code is recognized only in plain text. Inside a link label it would nest an <a> in an <a>, and
// the renderer refuses there too — but the label arrives here already carrying the link mark, so
// splitting is skipped for it.
function textWithRefs(text: string, marks: Mark[]): JSONContent[] {
  if (marks.some((mark) => mark.type === 'link')) return [textNode(text, marks)]

  const parts: JSONContent[] = []
  let cursor = 0
  for (const match of text.matchAll(REF_CODE)) {
    const start = match.index ?? 0
    if (start > cursor) parts.push(textNode(text.slice(cursor, start), marks))
    parts.push(refNode(match[0]))
    cursor = start + match[0].length
  }
  if (!parts.length) return [textNode(text, marks)]
  if (cursor < text.length) parts.push(textNode(text.slice(cursor), marks))
  return parts
}

function textNode(text: string, marks: Mark[]): JSONContent {
  return marks.length ? { type: 'text', text, marks: marks.map((mark) => ({ ...mark })) } : { type: 'text', text }
}

function refNode(code: string): JSONContent {
  return { type: 'entityRef', attrs: { code: canonicalCode(code) } }
}
