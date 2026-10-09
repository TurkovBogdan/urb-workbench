/**
 * "What's inside" in one line — for dialogs that ask about deletion.
 *
 * A workspace doesn't know what it holds: the counters are declared by the modules on top, and
 * their set depends on the app's composition. So the text is assembled from what arrived rather
 * than written in the dictionary as a list of zones and tasks — otherwise every new module would
 * have to edit someone else's phrase.
 *
 * The label is taken by the counter's key (`label_key`) from the owning module's dictionary, as a
 * plural declined by the number — the same words the list row puts after its numbers.
 */

import type { WorkspaceListRow } from './api'

type Translate = (key: string, count: number) => string

/** Whether there is anything inside: zeros are not shown — an empty workspace says just that. */
export function hasContent(workspace: WorkspaceListRow | null): boolean {
  return (workspace?.counters ?? []).some((counter) => counter.count > 0)
}

/** "2 groups, 12 tasks" — non-zero only, in the order the backend set. */
export function contentSummary(
  workspace: WorkspaceListRow | null,
  t: Translate,
): string {
  return (workspace?.counters ?? [])
    .filter((counter) => counter.count > 0)
    .map((counter) => `${counter.count} ${t(counter.label_key, counter.count)}`)
    .join(', ')
}
