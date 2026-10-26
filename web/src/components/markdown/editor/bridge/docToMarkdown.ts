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
import { DIAGRAM_LANGUAGE } from '../../shared/contracts'

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

    case 'diagram':
      return fenced(String(node.attrs?.source ?? ''), DIAGRAM_LANGUAGE)

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
// Delimiters open when the set of marks changes and close in reverse order — like tags. Of the
// marks opening at one node, the one whose run lasts longer opens first, outside: in `***a** b*`
// the italic outlives the bold, and opened inside it would have to close with the bold and open
// again in front of the blank, where an asterisk opens nothing. MARK_ORDER settles a tie.
const MARK_ORDER = ['link', 'bold', 'italic', 'strike']

interface Wrap { key: string; open: string; close: string; emphasis: boolean }

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
      out.push({ key: `link|${href}`, open: '[', close: `](${href})`, emphasis: false })
    } else if (name === 'bold') out.push({ key: 'bold', open: '**', close: '**', emphasis: true })
    else if (name === 'italic') out.push({ key: 'italic', open: '*', close: '*', emphasis: true })
    else out.push({ key: 'strike', open: '~~', close: '~~', emphasis: true })
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

// A code ends as a word of its own. A pill the document holds right before a letter, a digit or
// another pill — text pasted after it, a word typed there — would otherwise print glued: before a
// hex letter or digit (`FILE@`, `CODEX@` begin with one) the code reads as no code at all, before
// any other letter it reads as one word to the person and to an agent reading the body. The space
// carries the pill's marks, so a bold run around the pill stays one run. Nothing changes where
// anything is printed between the two already — a delimiter, a backtick, punctuation, a blank —
// nor before a code: a code has no boundary on the left (`REF_CODE`). Such texts keep their bytes.
const WORD_START = /^[\p{L}\p{N}\p{M}]/u

function startsWord(node: JSONContent): boolean {
  if (node.type === 'entityRef') return true
  return node.type === 'text' && !hasMark(node, 'code') && WORD_START.test(node.text ?? '')
}

function wrapKeys(node: JSONContent): string {
  return wraps(node).map((wrap) => wrap.key).join('|')
}

function separatedRefs(nodes: JSONContent[]): JSONContent[] {
  const out: JSONContent[] = []
  nodes.forEach((node, index) => {
    const previous = nodes[index - 1]
    if (previous?.type === 'entityRef' && startsWord(node) && wrapKeys(previous) === wrapKeys(node)) {
      out.push(previous.marks?.length ? { type: 'text', text: ' ', marks: previous.marks } : plain(' '))
    }
    out.push(node)
  })
  return out
}

/** Index of the first node from `start` on that no longer carries the wrap `key`. */
function runEnd(plan: Wrap[][], start: number, key: string): number {
  let end = start
  while (end < plan.length && plan[end].some((wrap) => wrap.key === key)) end += 1
  return end
}

function inline(nodes: JSONContent[] | undefined): string {
  const flat = liftEdgeSpaces(merged(separatedRefs(nodes ?? [])))
  const plan = flat.map(wraps)
  let out = ''
  let active: Wrap[] = []
  // The blank a node ended with, held until it is known whether delimiters close after it.
  let held = ''

  // Innermost first. The held blank leaves through the emphasis delimiters next to it: an asterisk
  // after a blank closes nothing. A link keeps it — `[text ](url)` reads back the same.
  const closeFrom = (keep: number): void => {
    for (let i = active.length - 1; i >= keep; i -= 1) {
      if (!active[i].emphasis) { out += held; held = '' }
      out += active[i].close
    }
    out += held
    held = ''
    active = active.slice(0, keep)
  }

  flat.forEach((node, index) => {
    const want = plan[index]
    // Marks still wanted stay open in the order they were opened, whatever their place in
    // MARK_ORDER: `*italic **bold** italic*` must not close the italic run to open the bold one.
    let keep = 0
    while (keep < active.length && want.some((wrap) => wrap.key === active[keep].key)) keep += 1
    closeFrom(keep)

    const opening = want
      .filter((wrap) => !active.some((open) => open.key === wrap.key))
      .sort((a, b) => runEnd(plan, index, b.key) - runEnd(plan, index, a.key))
    const { lead, body, trail } = content(node)
    // The leading blank goes ahead of the emphasis delimiters next to it, for the same reason.
    const lastLink = opening.map((wrap) => wrap.emphasis).lastIndexOf(false)
    let opens = ''
    opening.forEach((wrap, at) => {
      if (at === lastLink + 1) opens += lead
      opens += wrap.open
      active.push(wrap)
    })
    if (lastLink + 1 >= opening.length) opens += lead
    out += opens + body
    held = trail
  })

  closeFrom(0)
  return out
}

interface Printed { lead: string; body: string; trail: string }

function content(node: JSONContent): Printed {
  const whole = (body: string): Printed => ({ lead: '', body, trail: '' })
  if (node.type === 'entityRef') return whole(String(node.attrs?.code ?? ''))
  // Two spaces are the only line break markdown knows inside a paragraph.
  if (node.type === 'hardBreak') return whole('  \n')
  // The URL prints as is, unescaped: an underscore or asterisk inside a URL is part of the
  // address, and a backslash before it would break it.
  if (isAutolink(node)) return whole(node.text ?? '')
  if (node.type !== 'text') return whole('')
  // Nothing is escaped inside code — the code span itself is the escaping.
  if (hasMark(node, 'code')) return whole(codeSpan(node.text ?? ''))
  const value = node.text ?? ''
  const lead = /^\s*/.exec(value)?.[0] ?? ''
  const trail = lead.length === value.length ? '' : /\s*$/.exec(value)?.[0] ?? ''
  return { lead, body: escapeText(value.slice(lead.length, value.length - trail.length)), trail }
}

// Only emphasis has edges to lift: a link survives edge spaces (`[ text ](url)` reads back the
// same), an asterisk does not.
const EMPHASIS = ['bold', 'italic', 'strike']

function plain(value: string): JSONContent {
  return { type: 'text', text: value }
}

function hasMark(node: JSONContent, type: string): boolean {
  return (node.marks ?? []).some((mark) => mark.type === type)
}

function withoutMark(node: JSONContent, type: string): JSONContent {
  const { marks: all, ...rest } = node
  const marks = (all ?? []).filter((mark) => mark.type !== type)
  return marks.length ? { ...rest, marks } : rest
}

// Spaces at the edges of an emphasized run are moved outside. Per CommonMark a closing asterisk
// after a space closes nothing — `**word **` would spill over the rest of the paragraph. Edges
// are found for the run as a whole, not per node: otherwise a space inside
// `**bold `code` text**` would also be taken for an edge. And they are found per mark, not per
// set of marks: in `**bold *italic* bold**` the italic run's edge is not the bold run's, and
// lifting the space out of both split the bold run in three.
function liftEdgeSpaces(nodes: JSONContent[]): JSONContent[] {
  let out = nodes
  // A run of nothing but spaces stays unmarked — there is nothing to emphasize. Before the next
  // pass the text emptied by this one goes, and blanks it split off rejoin their neighbours: a run
  // edge hidden behind an empty node, or spread over two, would be only half lifted. A blank lifted
  // out of an inner mark can land on the edge of an outer one already passed, so the passes repeat
  // until nothing moves; each only takes marks off blanks, so that comes soon.
  for (let round = 0; round <= EMPHASIS.length; round += 1) {
    const before = JSON.stringify(out)
    for (const type of EMPHASIS) {
      out = merged(liftEdgesOf(out, type).filter((node) => !(node.type === 'text' && node.text === '')))
    }
    if (JSON.stringify(out) === before) break
  }
  return out
}

function liftEdgesOf(nodes: JSONContent[], type: string): JSONContent[] {
  const out: JSONContent[] = []

  for (let i = 0; i < nodes.length;) {
    if (!hasMark(nodes[i], type)) {
      out.push(nodes[i])
      i += 1
      continue
    }
    let end = i
    while (end < nodes.length && hasMark(nodes[end], type)) end += 1
    const run = nodes.slice(i, end)
    i = end

    const head = run[0]
    if (head.type === 'text') {
      const lead = /^\s*/.exec(head.text ?? '')?.[0] ?? ''
      if (lead) {
        out.push(withoutMark({ ...head, text: lead }, type))
        run[0] = { ...head, text: (head.text ?? '').slice(lead.length) }
      }
    }

    let trail: JSONContent | null = null
    const tail = run[run.length - 1]
    if (tail.type === 'text') {
      const spaces = /\s*$/.exec(tail.text ?? '')?.[0] ?? ''
      if (spaces) {
        trail = withoutMark({ ...tail, text: spaces }, type)
        run[run.length - 1] = { ...tail, text: (tail.text ?? '').slice(0, (tail.text ?? '').length - spaces.length) }
      }
    }

    out.push(...run)
    if (trail) out.push(trail)
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
