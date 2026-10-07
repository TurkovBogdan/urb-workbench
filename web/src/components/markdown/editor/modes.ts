// What the editor can do at this point of use.
//
// The fields people write into differ by nature. A task body has headings, lists and tables; a
// stage title has only text with emphasis. One editor for both cases works on one condition only:
// **the editor must not be able to express more than the storage accepts and the reader
// expects**. The feature set is therefore not styling but part of the field's contract.
//
// The set acts on four layers at once, and that is the whole point of keeping it as one list:
//
//   1. schema — a disabled node does not exist in the document, rather than "it is there but has
//      no button";
//   2. parsing — incoming markdown is reduced to what is allowed (bridge/restrict.ts), so pasting
//      foreign text cannot smuggle a construct past the schema;
//   3. chrome — the slash menu and the toolbar show exactly what will work;
//   4. printing — there is nothing to print that is not in the document.
//
// Without point 2 the rest are useless: the user pastes a heading from the clipboard, the schema
// rejects it, and ProseMirror refuses the WHOLE document at once.

/** Block constructs. The paragraph is not listed: it is always present and cannot be disabled. */
export type BlockFeature = 'heading' | 'list' | 'quote' | 'codeBlock' | 'divider' | 'table'

/** Inline: text marks and the entity reference pill. */
export type InlineFeature = 'bold' | 'italic' | 'strike' | 'code' | 'link' | 'entityRef'

/** Chrome: the block drag handle and the slash menu. */
export type ChromeFeature = 'handle' | 'slash'

export type Feature = BlockFeature | InlineFeature | ChromeFeature

export const BLOCK_FEATURES: readonly BlockFeature[] = [
  'heading', 'list', 'quote', 'codeBlock', 'divider', 'table',
]

export const INLINE_FEATURES: readonly InlineFeature[] = [
  'bold', 'italic', 'strike', 'code', 'link', 'entityRef',
]

/** Ready-made sets. The mode name is what goes into the markup; the list is what it means. */
export type EditorMode = 'full' | 'simple'

const FULL: readonly Feature[] = [...BLOCK_FEATURES, ...INLINE_FEATURES, 'handle', 'slash']

// Simple mode: paragraph, bold, italic — and nothing else. There are no block constructs at all,
// hence no chrome either: there is nothing to drag, and the slash menu would open empty. In such
// a field the slash becomes an ordinary character again.
const SIMPLE: readonly Feature[] = ['bold', 'italic']

export const MODES: Record<EditorMode, readonly Feature[]> = {
  full: FULL,
  simple: SIMPLE,
}

export type FeatureSet = ReadonlySet<Feature>

/**
 * Resolve a mode and point adjustments to it into one set.
 *
 * `features` replaces the mode's list entirely rather than extending it: "mode plus a bit" reads
 * ambiguously exactly where unambiguity matters — when answering "what does this field accept".
 */
export function resolveFeatures(mode: EditorMode = 'full', features?: readonly Feature[]): FeatureSet {
  return new Set(features ?? MODES[mode])
}
