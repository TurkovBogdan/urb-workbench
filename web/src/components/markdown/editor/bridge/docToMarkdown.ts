// Flat document → markdown: the printing half of the bridge.
//
// This is the half that decides whether the editor can be pointed at a real body. The flat schema
// (blocks.ts) settles half the question: there is no tree to fold, one block goes onto one line.
// But the model still does not keep the document's *spelling* — which marker, which fence, which
// escaping — so the goal is not "byte for byte", which no structural editor achieves, but a
// contract that can be held:
//
//   1. the second pass equals the first (stability);
//   2. the text does not change — no escaping is added that the parser did not require;
//   3. whatever cannot be carried is visible, not silent (see UNSUPPORTED in markdownToDoc.ts).
//
// Checked in both directions by the round-trip panel on the design-system page.
import type { JSONContent } from '@tiptap/core'
import { escapeLineStarts, escapeText } from './escape'

export function docToMarkdown(doc: JSONContent): string {
  return (doc.content ?? [])
    .map((node) => block(node))
    .filter((text) => text.length > 0)
    .join('\n\n')
}

function block(node: JSONContent): string {
  switch (node.type) {
    case 'paragraph':
      return escapeLineStarts(inline(node.content))

    case 'heading':
      return `${'#'.repeat(Number(node.attrs?.level ?? 1))} ${inline(node.content)}`

    // A quote is a line block, not a container: adjacent quotes print as adjacent quote
    // paragraphs and read back as the same.
    case 'quote':
      return `> ${escapeLineStarts(inline(node.content))}`

    case 'codeBlock':
      return fenced(text(node.content), String(node.attrs?.language ?? '') || '')

    case 'horizontalRule':
      return '---'

    case 'list':
      return listLines(node.content ?? [])

    case 'table':
      return tableLines(node)

    default:
      return ''
  }
}

// ── Table ─────────────────────────────────────────────────────────────────────

// The only block printed over SEVERAL lines, and the only one where that costs nothing: the shape
// is set by the format itself — header, delimiter, rows — so the printer has no choice to make.
// The width is taken from the header: it is what declares the column count in markdown, and GFM
// would read a row that diverges from it differently from how it looks in the editor.
function tableLines(node: JSONContent): string {
  const sections = node.content ?? []
  const headRow = sections.find((section) => section.type === 'tableHead')?.content?.[0]
  if (!headRow) return ''

  const bodyRows = sections.find((section) => section.type === 'tableBody')?.content ?? []
  const align = (node.attrs?.align ?? []) as (string | null)[]
  const width = (headRow.content ?? []).length

  return [
    tableRow(headRow, width),
    delimiterRow(align, width),
    ...bodyRows.map((row) => tableRow(row, width)),
  ].join('\n')
}

function tableRow(row: JSONContent, width: number): string {
  const cells = Array.from({ length: width }, (_, index) => cellText((row.content ?? [])[index]))
  return `| ${cells.join(' | ')} |`
}

// The delimiter row carries column alignment — a colon on the side the content is aligned to.
function delimiterRow(align: (string | null)[], width: number): string {
  const cells = Array.from({ length: width }, (_, index) => {
    if (align[index] === 'left') return ':---'
    if (align[index] === 'center') return ':---:'
    if (align[index] === 'right') return '---:'
    return '---'
  })
  return `| ${cells.join(' | ')} |`
}

function cellText(cell: JSONContent | undefined): string {
  const value = inline(cell?.content)
    // A pipe inside a cell must be escaped: GFM splits a line into cells BEFORE parsing inline
    // markup, so an unescaped pipe would break the row — including one inside a backtick code
    // span, where it looks harmless.
    .replace(/\|/g, '\\|')
    // A line break inside a cell cannot be expressed in markdown at all: a row is one line. A soft
    // break (Shift+Enter) collapses into a space instead of breaking the table.
    .replace(/\s*\n\s*/g, ' ')
    .trim()
  // An empty cell prints as a space: `| |` reads as a cell, while `||` reads as a neighbour's edge.
  return value || ' '
}

// The flat row of items is turned back into indentation. The indent width comes from the
// ancestors' markers, not a fixed two: under `10. ` content starts at the fourth column, and a
// two-space indent would detach the nested item from its parent.
function listLines(items: JSONContent[]): string {
  const counters: number[] = []
  const widths: number[] = []
  const lines: string[] = []
  let previousDepth = -1

  for (const item of items) {
    const depth = Math.max(0, Number(item.attrs?.depth ?? 0))
    const checked = (item.attrs?.checked ?? null) as boolean | null
    const ordered = Boolean(item.attrs?.ordered)

    if (depth > previousDepth) counters[depth] = 0
    counters.length = depth + 1
    widths.length = Math.max(widths.length, depth + 1)
    previousDepth = depth

    let marker: string
    if (checked !== null) {
      marker = `- [${checked ? 'x' : ' '}] `
      counters[depth] = 0
      // A checkbox item's content starts right after `- `: the checkbox itself is part of it.
      widths[depth] = 2
    } else if (ordered) {
      counters[depth] = (counters[depth] ?? 0) + 1
      marker = `${counters[depth]}. `
      widths[depth] = marker.length
    } else {
      counters[depth] = 0
      marker = '- '
      widths[depth] = 2
    }

    let indent = ''
    for (let level = 0; level < depth; level += 1) indent += ' '.repeat(widths[level] ?? 2)
    lines.push(indent + marker + escapeLineStarts(inline(item.content)))
  }

  return lines.join('\n')
}

// The fence must be longer than the longest backtick run inside, or the block ends early.
function fenced(code: string, language: string): string {
  const runs = [...code.matchAll(/`{3,}/g)].map((match) => match[0].length + 1)
  const fence = '`'.repeat(Math.max(3, ...runs))
  return `${fence}${language}\n${code}\n${fence}`
}

function text(nodes: JSONContent[] | undefined): string {
  return (nodes ?? []).map((node) => node.text ?? '').join('')
}

// Marks are printed in RUNS, not per node. Tiptap stores `**bold `code` text**` as three adjacent
// nodes carrying the same mark, and wrapping each one separately would give
// `**bold** `code` **text**` — the same on screen, different in the text, and so on every save.
// Delimiters open when the set of marks changes and close in reverse order — like tags.
const MARK_ORDER = ['link', 'bold', 'italic', 'strike']

interface Wrap { key: string; open: string; close: string }

// A link whose text equals its address is a bare URL, not a markdown link. Parsing enables
// `linkify`, so an `https://…` written in the text arrives here ALREADY as a node with a link;
// printing it in the full `[url](url)` form would make text the person never wrote appear in
// their body by itself. On real bodies that is 25 lines rewritten out of nothing.
function isAutolink(node: JSONContent): boolean {
  if (node.type !== 'text') return false
  const marks = node.marks ?? []
  if (marks.length !== 1 || marks[0].type !== 'link') return false
  return (node.text ?? '') === String(marks[0].attrs?.href ?? '')
}

function wraps(node: JSONContent): Wrap[] {
  if (isAutolink(node)) return []
  const marks = node.marks ?? []
  const out: Wrap[] = []
  for (const name of MARK_ORDER) {
    const mark = marks.find((item) => item.type === name)
    if (!mark) continue
    if (name === 'link') {
      const href = String(mark.attrs?.href ?? '')
      out.push({ key: `link|${href}`, open: '[', close: `](${href})` })
    } else if (name === 'bold') out.push({ key: 'bold', open: '**', close: '**' })
    else if (name === 'italic') out.push({ key: 'italic', open: '*', close: '*' })
    else out.push({ key: 'strike', open: '~~', close: '~~' })
  }
  return out
}

// Two adjacent text nodes with identical marks are one stretch of text; Tiptap splits them
// routinely, a transaction boundary is enough. Merging comes before everything else: run edges are
// found from it, and it is also what prevents a gratuitous `**a****b**`.
function merged(nodes: JSONContent[]): JSONContent[] {
  const out: JSONContent[] = []
  for (const node of nodes) {
    const last = out[out.length - 1]
    if (node.type === 'text' && last?.type === 'text' && sameMarks(last, node)) {
      out[out.length - 1] = { ...last, text: (last.text ?? '') + (node.text ?? '') }
      continue
    }
    out.push(node)
  }
  return out
}

function sameMarks(a: JSONContent, b: JSONContent): boolean {
  return JSON.stringify(a.marks ?? []) === JSON.stringify(b.marks ?? [])
}

function inline(nodes: JSONContent[] | undefined): string {
  let out = ''
  let active: Wrap[] = []

  for (const node of liftEdgeSpaces(merged(nodes ?? []))) {
    const want = wraps(node)
    let keep = 0
    while (keep < active.length && keep < want.length && active[keep].key === want[keep].key) keep += 1
    for (let i = active.length - 1; i >= keep; i -= 1) out += active[i].close
    active = active.slice(0, keep)
    for (let i = keep; i < want.length; i += 1) { out += want[i].open; active.push(want[i]) }
    out += content(node)
  }

  for (let i = active.length - 1; i >= 0; i -= 1) out += active[i].close
  return out
}

function content(node: JSONContent): string {
  if (node.type === 'entityRef') return String(node.attrs?.code ?? '')
  // Two spaces are the only line break markdown knows inside a paragraph.
  if (node.type === 'hardBreak') return '  \n'
  // The URL prints as is, unescaped: an underscore or asterisk inside a URL is part of the
  // address, and a backslash before it would break it.
  if (isAutolink(node)) return node.text ?? ''
  if (node.type !== 'text') return ''
  // Nothing is escaped inside code — the code span itself is the escaping.
  const code = (node.marks ?? []).some((mark) => mark.type === 'code')
  return code ? codeSpan(node.text ?? '') : escapeText(node.text ?? '')
}

// Emphasis is keyed on these marks only: a link survives edge spaces (`[ text ](url)` reads back
// the same), an asterisk does not.
function emphasisKey(node: JSONContent): string {
  return (node.marks ?? [])
    .filter((mark) => mark.type === 'bold' || mark.type === 'italic' || mark.type === 'strike')
    .map((mark) => mark.type)
    .sort()
    .join(',')
}

function plain(value: string): JSONContent {
  return { type: 'text', text: value }
}

// Spaces at the edges of an emphasized run are moved outside. Per CommonMark a closing asterisk
// after a space closes nothing — `**word **` would spill over the rest of the paragraph. Edges
// are found for the run as a whole, not per node: otherwise a space inside
// `**bold `code` text**` would also be taken for an edge.
function liftEdgeSpaces(nodes: JSONContent[]): JSONContent[] {
  const out: JSONContent[] = []

  for (let i = 0; i < nodes.length;) {
    const key = emphasisKey(nodes[i])
    let end = i
    while (end < nodes.length && emphasisKey(nodes[end]) === key) end += 1
    let run = nodes.slice(i, end)
    i = end

    if (!key) {
      out.push(...run)
      continue
    }

    const head = run[0]
    if (head.type === 'text') {
      const lead = /^\s*/.exec(head.text ?? '')?.[0] ?? ''
      if (lead) {
        out.push(plain(lead))
        run = [{ ...head, text: (head.text ?? '').slice(lead.length) }, ...run.slice(1)]
      }
    }

    let trail = ''
    const tail = run[run.length - 1]
    if (tail?.type === 'text') {
      trail = /\s*$/.exec(tail.text ?? '')?.[0] ?? ''
      if (trail) {
        const kept = (tail.text ?? '').slice(0, (tail.text ?? '').length - trail.length)
        run = [...run.slice(0, -1), { ...tail, text: kept }]
      }
    }

    // A run of nothing but spaces stays unmarked — there is nothing to emphasize.
    out.push(...run.filter((node) => !(node.type === 'text' && node.text === '')))
    if (trail) out.push(plain(trail))
  }

  return out
}

function codeSpan(value: string): string {
  const runs = [...value.matchAll(/`+/g)].map((match) => match[0].length + 1)
  const fence = '`'.repeat(Math.max(1, ...runs))
  // A span starting or ending with a backtick needs a space — the parser strips it back off.
  const pad = value.startsWith('`') || value.endsWith('`') ? ' ' : ''
  return `${fence}${pad}${value}${pad}${fence}`
}
