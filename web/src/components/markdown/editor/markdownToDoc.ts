// Markdown → плоский документ: разбирающая половина моста.
//
// Токены даёт markdown-it — тот же, что рендерит тела, поэтому конструкция, понятная
// рендереру, понятна и редактору, а определение кода сущности (REF_CODE) остаётся одно на всё
// приложение. Дерево markdown-it здесь сплющивается в ряд блоков по правилам схемы (blocks.ts):
// вложенный список становится пунктом с большим `depth`, абзац цитаты — блоком `quote`.
//
// Печатающая половина живёт в docToMarkdown.ts; порознь им верить нельзя, поэтому страница
// дизайн-системы гоняет их друг против друга и показывает расхождение.
import MarkdownIt from 'markdown-it'
import type { Token } from 'markdown-it'
import type { JSONContent } from '@tiptap/core'
import { REF_CODE } from '../render'

// Чего мост не переносит. Выбрасывается на входе — значит, видно в круговом проходе, а не
// обнаруживается однажды в сохранённом теле.
export const UNSUPPORTED = ['tables', 'images', 'footnotes', 'raw HTML', 'blocks inside list items'] as const

// Код в бэктиках, где кроме кода ничего нет, — это ссылка, а не литерал; рендерер решает так же
// (render.ts, WHOLE_CODE_SPAN), и разойтись они не могут, иначе пилюля поменяет смысл на входе.
const WHOLE_CODE_SPAN = new RegExp(`^(?:${REF_CODE.source})$`)

// `breaks: false` — одиночный перенос внутри абзаца в теле незначим, поэтому приходит пробелом,
// а абзац переносится заново на выходе. Единственная нормализация, которую мост делает сознательно.
const md = new MarkdownIt({ html: false, linkify: true, breaks: false })
md.linkify.set({ fuzzyLink: false, fuzzyEmail: false })

// GFM-чеклист: правила для него у markdown-it нет, маркер по-прежнему лежит первым в абзаце
// пункта. Зеркалит TASK_MARKER из render.ts.
const TASK_MARKER = /^\[([ xX])\]\s+/

// Неподдерживаемую конструкцию надо пропускать целиком: выбросив только её собственные токены,
// мы оставили бы содержимое ячеек — текст таблицы упал бы в предыдущий блок.
const SKIPPED_CONTAINERS = new Set(['table_open'])

type Mark = { type: string; attrs?: Record<string, unknown> }

export function markdownToDoc(markdown: string): JSONContent {
  const tokens = md.parse(markdown, {})
  const doc: JSONContent = { type: 'doc', content: [] }
  // Стек держит только открытый строчный блок: блоки не вкладываются, поэтому глубже двух
  // уровней он не бывает.
  const stack: JSONContent[] = [doc]
  const ordered: boolean[] = []
  let list: JSONContent | null = null
  let listDepth = 0
  let quoteDepth = 0
  let skipping = 0

  const top = (): JSONContent => stack[stack.length - 1]
  const inItem = (): boolean => top().type === 'listItem'
  const open = (node: JSONContent): void => {
    ;(doc.content ??= []).push(node)
    stack.push(node)
  }
  // Блок верхнего уровня, попавший внутрь пункта списка (код в пункте, вложенная цитата),
  // плоской схеме не годится и выбрасывается — см. UNSUPPORTED.
  const addBlock = (node: JSONContent): void => {
    if (!inItem()) (doc.content ??= []).push(node)
  }

  for (let i = 0; i < tokens.length; i += 1) {
    const token = tokens[i]

    if (skipping > 0) {
      skipping += token.nesting
      continue
    }
    if (SKIPPED_CONTAINERS.has(token.type)) {
      skipping = 1
      continue
    }

    switch (token.type) {
      case 'heading_open':
        open({ type: 'heading', attrs: { level: Number(token.tag.slice(1)) }, content: [] })
        break

      case 'paragraph_open':
        // Внутри пункта абзаца не существует: пункт хранит строчное содержимое напрямую.
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

      // Цитата — не контейнер, а признак блока: считаем только глубину, чтобы знать, каким
      // типом открывать абзацы внутри неё.
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
            // Вложенность markdown становится числом: уровень списка минус один.
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

  // Пустой документ ProseMirror не примет: `doc` требует хотя бы один блок.
  if (!doc.content?.length) doc.content = [{ type: 'paragraph' }]
  return doc
}

// Пункт — чеклистовый, если его абзац открывается `[ ]` / `[x]`. Маркер снимается и с токена,
// и с его первого ребёнка — ровно как это делает рендерер.
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

  // ProseMirror запрещает пустые текстовые узлы и отвергает ВЕСЬ документ, если встретит хоть
  // один — редактор молча остаётся пустым. markdown-it же выдаёт пустой `text` регулярно: на
  // стыке строчных токенов, в начале строки, открывающейся кодом. Отсев здесь, а не у каждого
  // источника: любой новый способ породить пустышку иначе снова обнулит документ.
  return out.filter((node) => node.type !== 'text' || (node.text ?? '').length > 0)
}

// Код распознаётся только в обычном тексте. Внутри метки ссылки он вложил бы <a> в <a>, и
// рендерер отказывается там тоже — но метка приезжает сюда уже с меткой ссылки, так что
// разбиение для неё пропускается.
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
  return { type: 'entityRef', attrs: { code } }
}
