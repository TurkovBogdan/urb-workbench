// Where a dragged note landed — one rule for every container of the codex tree.
//
// The neighbour is not read from the markup after the drop: `vue-draggable-plus` reverts the DOM
// reorder so that Vue redoes it from its own list, and a neighbour read after the revert is a
// neighbour in the old order. The place is computed from the library's `newIndex` over the
// container's codes with the moved note itself left out — the same whether the revert happened or
// not, and for a move into another container, where the note is simply not there yet.
// (`features/tasks/drag.ts` holds the same rule for the task list.)

/**
 * Codes of the container's live notes in order; the moved one left out. Deleted notes shown in the
 * tree are skipped: the library's `newIndex` counts draggable items only, and the backend places a
 * note among live siblings only — a deleted one holds no place in the row.
 */
function neighbours(container: HTMLElement, movedCode: string): string[] {
  return [...container.children]
    .filter((child) => child.classList.contains('codex-tree__item--note'))
    .map((child) => (child as HTMLElement).dataset?.code)
    .filter((code): code is string => !!code && code !== movedCode)
}

/** Code of the note the moved one landed BELOW; `null` — it became first. */
export function anchorAfterDrop(
  container: HTMLElement,
  movedCode: string,
  newIndex: number | undefined,
): string | null {
  // A codex row (`CodexDropZone`) has no places inside: the note goes to the END of the codex's top
  // level, after the note the row names as last.
  if (container.dataset.drop === 'end') return container.dataset.after || null
  if (!newIndex) return null
  return neighbours(container, movedCode)[newIndex - 1] ?? null
}

/** A note left the tree's own place: where it now hangs and after which sibling. */
export interface NoteDrop {
  code: string
  /** The codex (its top level) or the note it now hangs under. */
  parent: string
  after: string | null
}
