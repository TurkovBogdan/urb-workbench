// What the task fields are edited with.
//
// The editor's feature set is a decision about what a field ACCEPTS, and that is domain
// knowledge: a shared component has no business knowing that a task goal never has headings. So
// the sets are declared here, while `components/markdown/editor/modes.ts` holds only the generic
// `full` and `simple`.
//
// **No field has a drag handle, and that is forced.** The extension places the handle to the left
// of the block and needs a 36px column for it — but the field sits inside a card with a section
// heading, and that column would shift the text against the heading. Moving the handle into the
// card's padding is not possible either: its 16px are not enough. Blocks in task fields are
// rearranged by cut and paste, not by dragging.
import type { Feature } from '@/components/markdown/editor/modes'

/**
 * Brief and plan — everything the editor can do, except the handle.
 *
 * These hold reasoned prose: subsections, lists, code listings, comparison tables, references to
 * neighbouring entities. There is nothing to restrict here — this is exactly the set the renderer
 * displays.
 */
export const TASK_DOCUMENT_FEATURES: readonly Feature[] = [
  'heading', 'list', 'quote', 'codeBlock', 'divider', 'table',
  'bold', 'italic', 'strike', 'code', 'link', 'entityRef',
  'slash',
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
  'slash',
]
