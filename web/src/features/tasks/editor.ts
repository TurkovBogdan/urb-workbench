// What the task fields are edited with.
//
// The editor's feature set is a decision about what a field ACCEPTS, and that is domain
// knowledge: a shared component has no business knowing that a task goal never has headings. So
// the sets are declared here, while `components/markdown/editor/modes.ts` holds only the generic
// `full` and `simple`.
//
// **Every field with blocks has a drag handle** (the owner's call, 2026-10-12). The handle needs a
// 20px column left of the text; in a card with a section heading that column shifts the text off
// the heading, and the editor narrows the shift by borrowing 8px of the card's padding (see
// `.editor--handled` in MarkdownEditor.vue). One-line fields (`mode="simple"`) have no blocks and
// so no handle.
import type { Feature } from '@/components/markdown/editor/modes'

/**
 * Brief, plan, work, journal, a note's body — everything the editor can do.
 *
 * These hold reasoned prose: subsections, lists, code listings, diagrams, comparison tables,
 * references to neighbouring entities. There is nothing to restrict here — this is exactly the set
 * the renderer displays.
 */
export const TASK_DOCUMENT_FEATURES: readonly Feature[] = [
  'heading', 'list', 'quote', 'codeBlock', 'diagram', 'divider', 'table',
  'bold', 'italic', 'strike', 'code', 'link', 'entityRef',
  'slash', 'handle',
]

/**
 * Constraints and criteria are enumerations, not documents.
 *
 * A field a paragraph and a half long cannot have a heading: it would split into sections what is
 * already a single section. Tables and dividers are out of place there too. Lists stay — criteria
 * are almost always a list.
 */
export const TASK_BRIEF_FEATURES: readonly Feature[] = [
  'list',
  'bold', 'italic', 'strike', 'code', 'link', 'entityRef',
  'slash', 'handle',
]
