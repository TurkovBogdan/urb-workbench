// Привести разобранный документ к тому, что поле вообще принимает.
//
// Шаг обязателен, а не украшение. Схема режима не знает, например, заголовка — и если разбор
// всё-таки соберёт узел `heading`, ProseMirror отвергнет ВЕСЬ документ, а не один узел: поле
// молча останется пустым. Вставка чужого текста из буфера — самый обычный способ это устроить,
// поэтому фильтр стоит между разбором и схемой, а не рядом с кнопками.
//
// Правило понижения одно: **сохранить текст, потерять оформление**. Заголовок становится
// абзацем, а не исчезает; пункт списка — абзацем; блок кода — абзацем со своим текстом. Молча
// пропадает только то, у чего текста нет вовсе (линия) или чей текст без своей структуры
// превращается в кашу (таблица).
import type { JSONContent } from '@tiptap/core'
import type { FeatureSet } from '../modes'

export function restrict(doc: JSONContent, features: FeatureSet): JSONContent {
  const blocks: JSONContent[] = []
  for (const node of doc.content ?? []) blocks.push(...block(node, features))

  // Пустой документ ProseMirror не примет: `doc` требует хотя бы один блок. Дойти сюда пустым
  // можно — например, тело из одной таблицы в режиме, где таблиц нет.
  return { type: 'doc', content: blocks.length ? blocks : [{ type: 'paragraph' }] }
}

function block(node: JSONContent, features: FeatureSet): JSONContent[] {
  switch (node.type) {
    case 'heading':
      return features.has('heading')
        ? [withInline(node, features)]
        : [paragraph(inlineOf(node, features))]

    case 'quote':
      return features.has('quote')
        ? [withInline(node, features)]
        : [paragraph(inlineOf(node, features))]

    case 'list':
      if (features.has('list')) {
        return [{ ...node, content: (node.content ?? []).map((item) => withInline(item, features)) }]
      }
      // Уровень вложенности теряется вместе со списком: в абзаце его негде хранить, а
      // изображать отступ пробелами значило бы подменить структуру оформлением.
      return (node.content ?? []).map((item) => paragraph(inlineOf(item, features)))

    case 'codeBlock':
      if (features.has('codeBlock')) return [node]
      // Текст листинга остаётся текстом абзаца — без языка и без ограждения.
      return [paragraph((node.content ?? []).map((child) => ({ type: 'text', text: child.text ?? '' }))
        .filter((child) => (child.text ?? '').length > 0))]

    case 'horizontalRule':
      return features.has('divider') ? [node] : []

    case 'table':
      return features.has('table') ? [node] : []

    default:
      return [withInline(node, features)]
  }
}

function paragraph(content: JSONContent[]): JSONContent {
  return content.length ? { type: 'paragraph', content } : { type: 'paragraph' }
}

function withInline(node: JSONContent, features: FeatureSet): JSONContent {
  const content = inlineOf(node, features)
  return content.length ? { ...node, content } : { ...node, content: undefined }
}

function inlineOf(node: JSONContent, features: FeatureSet): JSONContent[] {
  const out: JSONContent[] = []
  for (const child of node.content ?? []) out.push(...inline(child, features))
  return out
}

function inline(node: JSONContent, features: FeatureSet): JSONContent[] {
  // Пилюля без своей возможности — обычный текст с кодом: код сущности остаётся читаемым и
  // по-прежнему уедет в тело, просто перестанет быть объектом.
  if (node.type === 'entityRef') {
    if (features.has('entityRef')) return [node]
    const code = String(node.attrs?.code ?? '')
    return code ? [{ type: 'text', text: code }] : []
  }

  if (node.type !== 'text') return [node]

  const marks = (node.marks ?? []).filter((mark) => isAllowed(mark.type, features))
  return marks.length ? [{ ...node, marks }] : [{ ...node, marks: undefined }]
}

// Имя метки в схеме и имя возможности совпадают у всех, кроме ссылки — у неё метка называется
// так же, так что таблица соответствий не нужна вовсе; функция существует ради явного отказа
// незнакомой метке, а не ради перевода имён.
function isAllowed(type: string | undefined, features: FeatureSet): boolean {
  if (!type) return false
  return features.has(type as never)
}
