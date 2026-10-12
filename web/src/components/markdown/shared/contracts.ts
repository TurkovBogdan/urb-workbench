// What the renderer and the editor are not allowed to disagree about.
//
// The two zones parse the same bodies with the same markdown-it, but they act on the result
// differently: one paints HTML, the other builds an editable document. Every place where they
// must recognise *the same thing* lives here, so a change lands in one file instead of two —
// a body where a pill renders but cannot be typed (or the reverse) is the failure this file
// exists to prevent.

// Entity cross-references: a `TYPE@<hash>` code in a body is a typed link to that entity — every
// type the backend lookup answers for (`core_lookup`). The order is free: `TASK` inside
// `TASKGROUP@…` fails on the `@` and the alternation backtracks to the whole word.
export const REF_TYPES = ['TASKGROUP', 'TASK', 'STAGE', 'JOURNAL', 'NOTE', 'WORKSPACE', 'CODEX'] as const

export type RefType = (typeof REF_TYPES)[number]

// Where a code leads before its preview has arrived. The preview's `link` is the address; this is
// the part of it the code alone can tell, so a pill is a link from the first paint. A stage, a
// journal entry and a task note live on their task's page, and the task is not in the code — they
// wait for the preview rather than lead to a guessed address. Part of the contract because both
// zones navigate: one address for both.
const REF_PATH: Record<RefType, ((code: string) => string) | null> = {
  TASK: (code) => `/tasks/task/${code}`,
  TASKGROUP: () => '/tasks/groups',
  WORKSPACE: () => '/workspaces',
  CODEX: (code) => `/codex/materials/${code}`,
  STAGE: null,
  JOURNAL: null,
  NOTE: null,
}

/** The address a canonical code leads to without its preview; `null` — only the preview knows. */
export function refPath(code: string): string | null {
  const type = code.split('@')[0] as RefType
  return REF_PATH[type]?.(code) ?? null
}

// Codes are exactly this many hex chars; the negative lookahead rejects a longer hex run, so a
// body still quoting a retired 22-char code reads as plain text rather than a dead link.
export const CODE_LEN = 10

// Carries the `g` flag: both zones scan a text node for every code in it, not just the first.
// Case-insensitive on purpose: codes are upper case now, but bodies written before still quote them
// in lower case and must keep resolving. Whoever takes a match folds it with `canonicalCode`.
export const REF_CODE = new RegExp(
  `(${REF_TYPES.join('|')})@([0-9a-f]{${CODE_LEN}})(?![0-9a-f])`,
  'gi',
)

/** The stored form of a matched code — upper case, as the API returns it. */
export function canonicalCode(code: string): string {
  return code.toUpperCase()
}

// A code reads as an identifier, so bodies routinely wrap it in backticks. A code span that is
// nothing but one code is still a reference, not a literal — anything else in the span (prose,
// a second code, a fragment) keeps it literal, and a fenced block stays code either way.
export const WHOLE_CODE_SPAN = new RegExp(
  `^(${REF_TYPES.join('|')})@([0-9a-f]{${CODE_LEN}})$`,
  'i',
)

/** The canonical code when `text` is exactly one code of the vocabulary, otherwise `null`. */
export function parseRefCode(text: string): string | null {
  const trimmed = text.trim()
  return WHOLE_CODE_SPAN.test(trimmed) ? canonicalCode(trimmed) : null
}

// GFM task list: markdown-it has no rule for it, so the marker is still sitting at the front of
// the list item's first paragraph when either zone gets the tokens. Both strip it the same way —
// the renderer turns it into a checkbox, the editor into the item's `checked` attribute.
export const TASK_MARKER = /^\[([ xX])\]\s+/

// The fence language that makes a code block a diagram. The renderer draws such a fence; the
// editor turns it into its diagram block and prints the block back as the same fence.
export const DIAGRAM_LANGUAGE = 'mermaid'
