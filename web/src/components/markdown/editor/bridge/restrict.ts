// Reduce a parsed document to what the field accepts at all.
//
// The step is mandatory, not decoration. A mode's schema may not know, say, a heading — and if
// parsing still produces a `heading` node, ProseMirror rejects the WHOLE document, not one node:
// the field silently stays empty. Pasting foreign text from the clipboard is the most ordinary way
// to cause that, so the filter sits between parsing and the schema, not next to the buttons.
//
// There is one downgrade rule: **keep the text, lose the formatting**. A heading becomes a
// paragraph instead of vanishing; a list item becomes a paragraph; a code block becomes a
// paragraph with its text. Only what has no text at all (a rule) or whose text turns into mush
// without its structure (a table) is dropped silently.
import type { JSONContent } from '@tiptap/core'
import type { FeatureSet } from '../modes'
import { DIAGRAM_LANGUAGE } from '../../shared/contracts'

export function restrict(doc: JSONContent, features: FeatureSet): JSONContent {
  const blocks: JSONContent[] = []
  for (const node of doc.content ?? []) blocks.push(...block(node, features))

  // ProseMirror will not accept an empty document: `doc` requires at least one block. Arriving
  // here empty is possible — e.g. a body made of a single table in a mode without tables.
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
      // The nesting level is lost along with the list: a paragraph has nowhere to keep it, and
      // faking the indent with spaces would substitute formatting for structure.
      return (node.content ?? []).map((item) => paragraph(inlineOf(item, features)))

    case 'codeBlock':
      if (features.has('codeBlock')) return [node]
      // The listing's text stays as paragraph text — without a language and without a fence.
      return [paragraph((node.content ?? []).map((child) => ({ type: 'text', text: child.text ?? '' }))
        .filter((child) => (child.text ?? '').length > 0))]

    // A field without diagrams still keeps the source: as the mermaid fence it was, when the field
    // has code blocks, otherwise as the paragraph text a code block falls back to.
    case 'diagram': {
      if (features.has('diagram')) return [node]
      const source = String(node.attrs?.source ?? '')
      return block({
        type: 'codeBlock',
        attrs: { language: DIAGRAM_LANGUAGE },
        content: source ? [{ type: 'text', text: source }] : [],
      }, features)
    }

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
  // A pill without its feature becomes plain text holding the code: the entity code stays
  // readable and still goes into the body, it just stops being an object.
  if (node.type === 'entityRef') {
    if (features.has('entityRef')) return [node]
    const code = String(node.attrs?.code ?? '')
    return code ? [{ type: 'text', text: code }] : []
  }

  if (node.type !== 'text') return [node]

  const marks = (node.marks ?? []).filter((mark) => isAllowed(mark.type, features))
  return marks.length ? [{ ...node, marks }] : [{ ...node, marks: undefined }]
}

// A mark's schema name and its feature name coincide for every mark, the link included — its mark
// carries the same name — so no mapping table is needed at all; the function exists to refuse an
// unknown mark explicitly, not to translate names.
function isAllowed(type: string | undefined, features: FeatureSet): boolean {
  if (!type) return false
  return features.has(type as never)
}
