// What a codex's rules and its notes are edited with — documents, like a task's brief and plan, so
// the same set: everything the renderer displays, the drag handle included (see the header of
// `features/tasks/editor.ts` for what the handle costs a field in a card).
import type { Feature } from '@/components/markdown/editor/modes'

export const CODEX_DOCUMENT_FEATURES: readonly Feature[] = [
  'heading', 'list', 'quote', 'codeBlock', 'diagram', 'divider', 'table',
  'bold', 'italic', 'strike', 'code', 'link', 'entityRef',
  'slash', 'handle',
]
