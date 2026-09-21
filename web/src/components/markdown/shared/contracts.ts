// What the renderer and the editor are not allowed to disagree about.
//
// The two zones parse the same bodies with the same markdown-it, but they act on the result
// differently: one paints HTML, the other builds an editable document. Every place where they
// must recognise *the same thing* lives here, so a change lands in one file instead of two —
// a body where a pill renders but cannot be typed (or the reverse) is the failure this file
// exists to prevent.

// Entity cross-references: a `TYPE@<hash>` code in a body is a typed link to that entity.
// The vocabulary is the set of types a code may carry; where each one leads is the renderer's
// business alone (REF_ROUTE in renderer/render.ts) and deliberately not part of this contract.
export const REF_TYPES = ['RESEARCH', 'AREA', 'NOTE', 'QUERY', 'SOURCE'] as const

// Codes are exactly this many hex chars; the negative lookahead rejects a longer hex run, so a
// body still quoting a retired 22-char code reads as plain text rather than a dead link.
export const CODE_LEN = 10

// Carries the `g` flag: both zones scan a text node for every code in it, not just the first.
export const REF_CODE = new RegExp(
  `(${REF_TYPES.join('|')})@([0-9a-f]{${CODE_LEN}})(?![0-9a-f])`,
  'g',
)

// A code reads as an identifier, so bodies routinely wrap it in backticks. A code span that is
// nothing but one code is still a reference, not a literal — anything else in the span (prose,
// a second code, a fragment) keeps it literal, and a fenced block stays code either way.
export const WHOLE_CODE_SPAN = new RegExp(
  `^(${REF_TYPES.join('|')})@([0-9a-f]{${CODE_LEN}})$`,
)

// GFM task list: markdown-it has no rule for it, so the marker is still sitting at the front of
// the list item's first paragraph when either zone gets the tokens. Both strip it the same way —
// the renderer turns it into a checkbox, the editor into the item's `checked` attribute.
export const TASK_MARKER = /^\[([ xX])\]\s+/
