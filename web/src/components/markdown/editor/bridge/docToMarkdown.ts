// Плоский документ → markdown: печатающая половина моста.
//
// Именно она решает, можно ли наводить редактор на настоящее тело. Плоская схема (blocks.ts)
// снимает половину вопроса: сворачивать дерево не нужно, один блок кладётся в одну строку. Но
// *написание* документа модель всё равно не хранит — какой маркер, какое ограждение, какое
// экранирование, — поэтому цель не «байт в байт», чего не достигает ни один структурный
// редактор, а контракт, который можно удержать:
//
//   1. второй проход равен первому (стабильность);
//   2. текст не меняется — не добавляется экранирование, которого не требовал парсер;
//   3. непереносимое видно, а не молчит (см. UNSUPPORTED в markdownToDoc.ts).
//
// Проверяется в обе стороны панелью кругового прохода на странице дизайн-системы.
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

    // Цитата — строчный блок, а не контейнер: соседние цитаты печатаются соседними абзацами
    // цитаты и такими же читаются обратно.
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

// ── Таблица ───────────────────────────────────────────────────────────────────

// Единственный блок, который печатается НЕСКОЛЬКИМИ строками, и единственный, где это ничего не
// стоит: форму задаёт сам формат — шапка, разделитель, ряды, — поэтому выбора у печати нет.
// Ширина берётся у шапки: она же объявляет число колонок в markdown, и ряд, разошедшийся с ней,
// GFM прочитал бы не так, как он выглядит в редакторе.
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

// Разделитель несёт выравнивание колонки — двоеточием с той стороны, к которой прижимают.
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
    // Вертикальная черта внутри ячейки обязана быть экранирована: GFM режет строку на ячейки ДО
    // разбора строчной разметки, поэтому неэкранированная черта развалила бы ряд — в том числе
    // из кода в бэктиках, где она выглядит безобидно.
    .replace(/\|/g, '\\|')
    // Перенос строки внутри ячейки в markdown не выражается вовсе: ряд — это одна строка.
    // Мягкий перенос (Shift+Enter) схлопывается в пробел, а не ломает таблицу.
    .replace(/\s*\n\s*/g, ' ')
    .trim()
  // Пустая ячейка печатается пробелом: `| |` читается ячейкой, а `||` — краем соседней.
  return value || ' '
}

// Плоский ряд пунктов превращается в отступы обратно. Ширина отступа берётся из маркеров
// предков, а не из фиксированной двойки: под `10. ` содержимое начинается на четвёртой
// колонке, и отступ в два пробела оторвал бы вложенный пункт от родителя.
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
      // Содержимое пункта-галочки начинается сразу за `- `: сама галочка — часть содержимого.
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

// Ограждение должно быть длиннее самой длинной череды бэктиков внутри, иначе блок кончится раньше.
function fenced(code: string, language: string): string {
  const runs = [...code.matchAll(/`{3,}/g)].map((match) => match[0].length + 1)
  const fence = '`'.repeat(Math.max(3, ...runs))
  return `${fence}${language}\n${code}\n${fence}`
}

function text(nodes: JSONContent[] | undefined): string {
  return (nodes ?? []).map((node) => node.text ?? '').join('')
}

// Метки печатаются ПРОГОНАМИ, а не поузлово. Tiptap хранит `**жирный `код` текст**` тремя
// соседними узлами с одной и той же меткой, и если обернуть каждый отдельно, получится
// `**жирный** `код` **текст**` — на экране то же самое, в тексте другое, и так на каждом
// сохранении. Ограничители открываются, когда набор меток меняется, и закрываются в обратном
// порядке — как теги.
const MARK_ORDER = ['link', 'bold', 'italic', 'strike']

interface Wrap { key: string; open: string; close: string }

// Ссылка, чей текст совпадает с адресом, — это голый адрес, а не ссылка в записи markdown.
// Разбор включает `linkify`, поэтому написанный в тексте `https://…` приезжает сюда УЖЕ узлом со
// ссылкой; напечатай мы его полной формой `[адрес](адрес)` — и текст, которого человек не писал,
// появился бы у него в теле сам. На реальных телах это 25 переписанных строк из ничего.
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

// Два соседних текстовых узла с одинаковыми метками — это один отрезок текста; Tiptap делит их
// рутинно, границы транзакции достаточно. Склейка нужна до всего остального: по ней ищутся края
// прогона, и она же убирает `**a****b**` на ровном месте.
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
  // Два пробела — единственный перенос строки, который markdown знает внутри абзаца.
  if (node.type === 'hardBreak') return '  \n'
  // Адрес печатается как есть, без экранирования: подчёркивание или звёздочка внутри URL —
  // часть адреса, и обратная косая черта перед ними его сломала бы.
  if (isAutolink(node)) return node.text ?? ''
  if (node.type !== 'text') return ''
  // Внутри кода ничего не экранируется — сам код и есть экранирование.
  const code = (node.marks ?? []).some((mark) => mark.type === 'code')
  return code ? codeSpan(node.text ?? '') : escapeText(node.text ?? '')
}

// Выделение считается только по этим меткам: ссылка краевые пробелы переживает (`[ текст ](url)`
// читается обратно тем же), а звёздочка — нет.
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

// Пробелы с краёв выделенного прогона выносятся наружу. Закрывающая звёздочка после пробела по
// CommonMark ничего не закрывает — `**слово **` расползлось бы на весь остаток абзаца. Границы
// ищутся у прогона целиком, а не у каждого узла: иначе пробел внутри `**жирный `код` текст**`
// тоже принялся бы за край.
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

    // Прогон из одних пробелов остаётся без разметки — выделять нечего.
    out.push(...run.filter((node) => !(node.type === 'text' && node.text === '')))
    if (trail) out.push(plain(trail))
  }

  return out
}

function codeSpan(value: string): string {
  const runs = [...value.matchAll(/`+/g)].map((match) => match[0].length + 1)
  const fence = '`'.repeat(Math.max(1, ...runs))
  // Спан, начинающийся или кончающийся бэктиком, требует пробела — парсер съест его обратно.
  const pad = value.startsWith('`') || value.endsWith('`') ? ' ' : ''
  return `${fence}${pad}${value}${pad}${fence}`
}
