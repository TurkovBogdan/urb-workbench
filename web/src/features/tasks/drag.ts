// Where a dragged row landed — one rule for every container of the task list.
//
// WHY NOT `previousElementSibling`. By the time `onEnd` fires, the markup is no longer what it
// was at the drop: `vue-draggable-plus` keeps the order in the array it was given and REVERTS the
// DOM reorder so that Vue redoes it from its own list. A neighbour read from the markup after the
// revert is a neighbour in the old order, i.e. the wrong position. The symptom is exactly this:
// you drag a row up and it moves down.
//
// So the position is computed from the library's `newIndex` and from the container's codes with
// the moved row itself excluded. The rule works the same whether the revert happened or not, and
// for a move into another container — there the moved row is simply not in the target row yet.

/** Codes of the container's rows in order; the moved row excluded. */
function neighbours(container: HTMLElement, movedCode: string): string[] {
  return [...container.children]
    .map((child) => (child as HTMLElement).dataset?.code)
    .filter((code): code is string => !!code && code !== movedCode)
}

/**
 * Code of the row the moved one landed BELOW; `null` — it became first.
 *
 * `newIndex` is the position among all rows of the container, so the row above it is the
 * `newIndex - 1`-th of the others.
 */
export function anchorAfterDrop(
  container: HTMLElement,
  movedCode: string,
  newIndex: number | undefined,
): string | null {
  // The group card header (`GroupDropZone`): it has no positions inside, so the task goes to the
  // END of the group's row — after the one the header named as last. `tasks_regroup` places a
  // task the same way.
  if (container.dataset.drop === 'end') {
    const last = container.dataset.after || null
    return last === movedCode ? null : last
  }
  if (!newIndex) return null
  return neighbours(container, movedCode)[newIndex - 1] ?? null
}
