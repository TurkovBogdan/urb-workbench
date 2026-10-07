import { computed, ref, watch } from 'vue'
import { defineStore } from 'pinia'

import { DEFAULT_PAGE_SIZE } from '@/constants/pagination'

import {
  deleteTask,
  listGroups,
  listTasks,
  reorderGroup as reorderGroupRequest,
  reorderTask,
  restoreTask,
  searchTasks,
  type GroupListRow,
  type TaskListRow,
} from '../api'
import { isTerminal } from '../labels'
import { byListOrder, childrenIndex, moveInRow, type MovePlace } from '../tree'
import { anyScope, MIN_DEEP_QUERY_LENGTH, NO_SCOPES, type TaskSearchScopes } from '../search'
import { useWorkspaceContextStore } from '@/features/workspace/stores/workspace-context.store'

/**
 * A branch node: the task, its depth and its children.
 *
 * The tree stays a tree rather than being flattened into one row, and the reason is dragging: a
 * sortable is created ON A CONTAINER, and a subtask's sibling row is its parent's children. A flat
 * list of rows provides no such container at all, so there was nothing to reorder a subtask among
 * its siblings with.
 *
 * `depth` and `last` stay here rather than being computed by the markup: they drive the indent and
 * the guide line's bend, and the row still needs to know nothing but its own place.
 */
export interface TaskNode {
  task: TaskListRow
  depth: number
  /** Last child of its parent: the guide line bends here instead of running through. */
  last: boolean
  children: TaskNode[]
}

/** A list section: a group, its top-level tasks and their branches. */
export interface TaskSection {
  group: GroupListRow | null
  tasks: TaskListRow[]
  /** The section's branches: one node per top-level task, children inside the node. */
  branches: TaskNode[]
}

/** The list display format. A second one (a board) will appear as a value here, not a branch in markup. */
export type TaskListFormat = 'list'

// The task list of the CURRENT workspace, laid out by group.
//
// The store neither picks nor stores the workspace — it reads it from the context
// (`workspace-context`), which lives in the sidebar header and outlives pages. That is why
// reloading on a workspace switch is the store's job, not the page's: the choice is changed from
// the sidebar while on any route, and a list that learned of it only on the next visit would show
// someone else's tasks.
//
// Groups arrive with a second request rather than being attached to tasks: a section is needed
// even when empty (the group exists but has no tasks yet), and such a group cannot be recovered
// from the tasks alone.
//
// FILTERS LIVE HERE, NOT IN THE URL. The URL holds only the open task (`?task=…`): it is what gets
// shared — "look at this". The filter set is the person's own working posture, not something sent
// to others, and if it were in the URL, every field edit would write a browser history entry, and
// "back" would rewind letters in the search instead of closing the task dialog.
//
// The client narrows the selection, not the backend (except for the trash). The workspace list
// arrives whole — hundreds of rows, not hundreds of thousands — and a filter over the set already
// received answers instantly with no network round trip. The exception is `include_deleted`:
// deleted tasks are not in the response at all, and there is no way to "show" them other than a
// new request.
export const useTasksStore = defineStore('tasks-tasks', () => {
  const context = useWorkspaceContextStore()

  const groups = ref<GroupListRow[]>([])
  const items = ref<TaskListRow[]>([])
  const loading = ref(true)
  const error = ref<unknown>(null)

  // Deliberately does not survive a tab reload — same as for workspaces: "show deleted" is a
  // one-off visit to the trash, not a mode of work.
  const includeDeleted = ref(false)

  const format = ref<TaskListFormat>('list')

  // ── Filters ─────────────────────────────────────────────────────────────────
  const query = ref('')
  // Status is a SET, priority a single value. The difference is not a whim: "show work and
  // reviews" is a common stance, while "show burning and frozen at once" means nothing.
  const statusFilter = ref<string[]>([])
  const priorityFilter = ref<string | null>(null)
  // There are no group or type filters. The list already shows groups as cards, each collapsible;
  // and type only changes the field set on the task page and answers none of the questions the
  // list is narrowed for.

  // Finished work is hidden by a DEFAULT, not a filter: the list answers "what to do", and done
  // work only takes up space in that answer. For the same reason `clearFilters` does not treat it
  // as "show everything" — reset restores the default rather than lifting it.
  const hideFinished = ref(true)

  // An explicit status choice beats the default: a person who ticked "Done" would get an empty list
  // if hiding kept working on top of their choice.
  const hideFinishedApplies = computed(
    () => hideFinished.value && !statusFilter.value.some(isTerminal),
  )

  // ── Search depth ────────────────────────────────────────────────────────────
  // Title and goal are searched right here, over the list already received. The brief, plan and
  // journal are not in the row at all — the search endpoint covers them, and it returns only codes:
  // intersecting with the list already at hand is cheaper than a second copy of the same cards.
  const searchScopes = ref<TaskSearchScopes>({ ...NO_SCOPES })
  /** Codes from the last deep query; `null` — there was none (no query or no scopes). */
  const deepCodes = ref<Set<string> | null>(null)

  const page = ref(1)
  const pageSize = ref(DEFAULT_PAGE_SIZE)

  // ── Collapsed groups ────────────────────────────────────────────────────────
  // A map of the person's EXPLICIT decisions for group cards and task branches — one for both,
  // because group codes (`TASKGROUP@…`) and task codes (`TASK@…`) never collide. "No group" uses the
  // empty string — exactly as the group filter does. What is not in the map is decided by the
  // default: an empty group arrives collapsed, a task branch expanded.
  //
  // The default is computed on the spot rather than written for every empty card: otherwise we
  // would have to expand the group ourselves the moment its first task is dragged in — i.e. keep in
  // two places a rule that already fits in one line.
  //
  // For now only for the page's lifetime: where to persist it between visits is `TASK@de5205ec30`.
  const folded = ref<Record<string, boolean>>({})

  function isCollapsed(code: string | null, empty = false): boolean {
    return folded.value[code ?? ''] ?? empty
  }

  /** Collapse or expand a group card. A new object, not a mutation: the reference is watched. */
  function toggleCollapsed(code: string | null, empty = false) {
    const key = code ?? ''
    folded.value = { ...folded.value, [key]: !isCollapsed(key, empty) }
  }

  // ── Gesture in progress ─────────────────────────────────────────────────────
  // A row is being held right now. Needed by whatever must quiet down meanwhile: tooltips of
  // buttons and glyphs popping up under the cursor as it travels over rows — they do not explain
  // the gesture but cover the target. The sortables themselves set and clear the flag (`TaskRows`,
  // `TaskSubtree`).
  const dragging = ref(false)

  // The gesture marker goes on `body`, not the list: Vuetify tooltips are teleported to the
  // document root. Here rather than in the list component — rows are dragged on the task page too,
  // and the marker is needed there as well. The rule that hides tooltips by it is in
  // `styles/main.scss`.
  watch(dragging, (on) => document.body.classList.toggle('tasks-dragging', on))

  /**
   * Code of the group's last top-level task — a task dropped on the card header lands after it.
   *
   * Computed over ALL tasks in the store, not the page: with pagination, the last row of a card on
   * screen is not the last in the group's row.
   */
  function lastRootOf(group: string | null): string | null {
    const row = items.value
      .filter((task) => task.parent_code === null && task.group_code === group)
      .sort(byListOrder)
    return row.length ? row[row.length - 1].code : null
  }

  /** No workspaces at all — tasks simply have nowhere to live, and the list is not to blame. */
  const noWorkspace = computed(() => context.loaded && !context.currentWorkspace)

  /**
   * The top level: tasks without a parent.
   *
   * A subtask in the main list used to stand on a par with its parent, and the same work read
   * twice — "Issue invoices" on top, then "Issue invoices → email template". The parent's card
   * expands the branch, while the list answers "what is there at all", and repetition in it is
   * noise.
   */
  const roots = computed(() => items.value.filter((task) => task.parent_code === null))

  const hasActiveFilters = computed(
    () =>
      query.value.trim() !== '' ||
      statusFilter.value.length > 0 ||
      priorityFilter.value !== null,
  )

  /**
   * The task is finished AND there is no live work left under it.
   *
   * The second condition is not decoration: hiding a done parent would also take off screen an
   * unclosed subtask under it (in the list it is shown as part of the branch, not on its own).
   */
  function finishedAndIdle(task: TaskListRow): boolean {
    if (!hideFinishedApplies.value || !isTerminal(task.status)) return false
    return !hasLiveDescendant(task)
  }

  function hasLiveDescendant(task: TaskListRow): boolean {
    return (childrenByParent.value.get(task.code) ?? []).some(
      (child) => !isTerminal(child.status) || hasLiveDescendant(child),
    )
  }

  function matches(task: TaskListRow): boolean {
    const needle = query.value.trim().toLowerCase()
    if (needle && !matchesQuery(task, needle)) return false
    if (statusFilter.value.length && !statusFilter.value.includes(task.status)) return false
    if (priorityFilter.value !== null && task.priority !== priorityFilter.value) return false
    if (finishedAndIdle(task)) return false
    return true
  }

  /**
   * Query match: the base is title and goal, visible in the row; deeper — codes from the search
   * endpoint. One OR the other: an enabled scope narrows nothing, it adds to the haystack.
   */
  function matchesQuery(task: TaskListRow, needle: string): boolean {
    if (task.title.toLowerCase().includes(needle)) return true
    if (task.description.toLowerCase().includes(needle)) return true
    return deepCodes.value?.has(task.code) ?? false
  }

  /**
   * What is listed before pagination.
   *
   * Without filters — the top level: subtasks will come under their parents as branches, and there
   * is no point paging them separately. With filters — ANY matching tasks, subtasks included, and
   * branches are not drawn: a subtask that matches must not vanish along with a parent that does
   * not, and one shown as a branch must not drag its whole lineage onto the screen.
   */
  const filtered = computed(() => {
    if (!hasActiveFilters.value) return roots.value.filter(matches)
    return items.value
      .filter(matches)
      .sort((left, right) => (layoutOrder.value.get(left.code) ?? 0) - (layoutOrder.value.get(right.code) ?? 0))
  })

  /**
   * Each task's place in the FULL layout: groups in their order, within a group the row of roots,
   * under each root its branch top to bottom.
   *
   * The flat filtered results need this. They cannot be sorted by a single `sort` as it comes from
   * the backend: for a root it is the position in ITS OWN group's row (`crud/link.py::_siblings`),
   * for a subtask the position among its parent's children, and numbers from different rows mean
   * nothing relative to each other. List cards do not care — a card has a single row — but a single
   * flat row does.
   *
   * Computed by traversal, not pairwise comparison: branch order is a tree traversal, and it cannot
   * be expressed as a comparator of two rows without a common ancestor anyway.
   */
  const layoutOrder = computed(() => {
    const index = new Map<string, number>()
    let place = 0
    const walk = (task: TaskListRow) => {
      index.set(task.code, place++)
      for (const child of childrenByParent.value.get(task.code) ?? []) walk(child)
    }
    const order = [...roots.value].sort(
      (left, right) =>
        groupRank(right.group_code) - groupRank(left.group_code) ||
        right.sort - left.sort ||
        (left.code < right.code ? -1 : 1),
    )
    order.forEach(walk)
    return index
  })

  /** A group's place in the layout; "No group" goes below all named ones, as in the sections. */
  function groupRank(code: string | null): number {
    if (!code) return Number.NEGATIVE_INFINITY
    return groups.value.find((group) => group.code === code)?.sort ?? 0
  }

  const total = computed(() => filtered.value.length)
  const pageCount = computed(() => Math.max(1, Math.ceil(total.value / pageSize.value)))

  /** Rows of the current page: they, not the whole result set, get laid out by group. */
  const pageItems = computed(() => {
    const from = (page.value - 1) * pageSize.value
    return filtered.value.slice(from, from + pageSize.value)
  })

  const isEmpty = computed(() => items.value.length === 0)

  /**
   * The default is hiding something RIGHT NOW — the workspace has finished tasks.
   *
   * Not the same as "the default is on": it is always on, and going by that would declare an empty
   * workspace "hidden by filters" — with a reset button that changes nothing, because reset
   * restores that very default.
   */
  const finishedHidden = computed(
    () => hideFinishedApplies.value && items.value.some((task) => isTerminal(task.status)),
  )

  /**
   * No rows, but not because there are no tasks: the filters hid them — and the answer to the
   * person is different. Go by what ACTUALLY narrows the results: an empty list with no filter at
   * all means "create the first one", and there is nothing to offer to reset.
   */
  const isFilteredOut = computed(
    () => (hasActiveFilters.value || finishedHidden.value) && total.value === 0,
  )

  /**
   * Layout by group: a section for EVERY group of the workspace plus "No group".
   *
   * Empty sections are shown, and that is not decoration: a task is moved by dragging it into
   * another card, and there is no way to move it into a group that is not on screen. So an empty
   * group is a gesture target, and without it the edit form would be the only way to file a task.
   * Empty ones sit at the BOTTOM and are muted (that is the markup's job): a move target must not
   * compete for attention with groups that have work.
   *
   * "No group" comes LAST and not alphabetically: it is not a topic on a par with the others but
   * the remainder — what has not been filed yet. Were it first, every visit to the list would start
   * with a heap of unsorted tasks, and the named groups — what groups exist for — would slide down.
   * It is also the target for "take out of a group", so it is shown even when empty.
   *
   * The exception is NARROWED results: a selected group is shown alone, and with any other filter
   * set all empty sections go away. The person is searching, not filing: they do not need a move
   * target now (branches are not drawn with filters at all), and a dozen empty cards around the
   * single hit is exactly what they asked to get out of sight.
   *
   * Order: groups with tasks first, then "No group" — if it holds anything — and only then the
   * empty ones. Unfiled work is still work and must not sit below empty move targets; an empty
   * remainder goes back to the very bottom, alongside the other empty ones.
   */
  const sections = computed<TaskSection[]>(() => {
    // No rows on the page — no sections either: otherwise a full set of empty headings would hang
    // under the "no tasks yet" message, and the answer to "what is here" would read twice.
    if (!pageItems.value.length) return []
    const byGroup = new Map<string, TaskListRow[]>()
    const loose: TaskListRow[] = []
    for (const task of pageItems.value) {
      if (!task.group_code) {
        loose.push(task)
        continue
      }
      const bucket = byGroup.get(task.group_code)
      if (bucket) bucket.push(task)
      else byGroup.set(task.group_code, [task])
    }
    const picked = hasActiveFilters.value
    const filled: TaskSection[] = []
    const empty: TaskSection[] = []
    for (const group of groups.value) {
      const tasks = byGroup.get(group.code)
      if (tasks) filled.push({ group, tasks, branches: branchesOf(tasks) })
      else if (!picked) empty.push({ group, tasks: [], branches: [] })
    }
    const unfiled: TaskSection = { group: null, tasks: loose, branches: branchesOf(loose) }
    const out = [...filled]
    if (loose.length) out.push(unfiled)
    out.push(...empty)
    // An empty remainder is a move target just like an empty group, and belongs with them, at the
    // bottom.
    if (!loose.length && (!picked || !out.length)) out.push(unfiled)
    return out
  })

  const childrenByParent = computed(() => childrenIndex(items.value))

  /**
   * Section roots → branches: a root followed by its descendants with depths. Branches are always
   * expanded — a task has only a few subtasks, and hiding them behind a disclosure would hide
   * exactly what the tree is shown for.
   *
   * With active filters branches are not built at all (see `filtered`): the screen shows a flat
   * list of matches where kinship adds nothing.
   */
  function branchesOf(roots: TaskListRow[]): TaskNode[] {
    const walk = (task: TaskListRow, depth: number, last: boolean): TaskNode => {
      // With filters the branch stops at the root: the screen shows a flat list of matches.
      if (hasActiveFilters.value) return { task, depth, last, children: [] }
      // What the default hides is hidden inside a branch too, otherwise a done subtask would vanish
      // from the top-level list yet remain under its parent — one task in two states. Everything
      // under it goes too: by the very condition there is nothing live there.
      const children = (childrenByParent.value.get(task.code) ?? []).filter(
        (child) => !finishedAndIdle(child),
      )
      return {
        task,
        depth,
        last,
        children: children.map((child, index) =>
          walk(child, depth + 1, index === children.length - 1),
        ),
      }
    }
    return roots.map((root) => walk(root, 0, true))
  }

  async function load() {
    // Workspaces may not have arrived yet (a visit via a direct link to the list): without them it
    // is not even known which workspace to ask for tasks.
    await context.ensure()
    const workspace = context.currentWorkspace?.code
    if (!workspace) {
      groups.value = []
      items.value = []
      error.value = null
      loading.value = false
      return
    }
    error.value = null
    try {
      // Both requests at once: section headings and their content are halves of one screen, and
      // waiting for them in turn would show an empty list during the second round trip.
      // `report: false` — a failed section read is shown by the page itself (SectionError).
      const [nextGroups, nextTasks] = await Promise.all([
        listGroups({ workspace }, { report: false }),
        listTasks({ workspace, include_deleted: includeDeleted.value }, { report: false }),
      ])
      groups.value = nextGroups
      items.value = nextTasks
    } catch (e) {
      error.value = e
    } finally {
      loading.value = false
    }
  }

  function showDeleted(enabled: boolean) {
    includeDeleted.value = enabled
    resetPage()
    return load()
  }

  /** Any filter edit returns to the first page: page five of the previous results is empty. */
  function resetPage() {
    page.value = 1
  }

  /**
   * Lift the default.
   *
   * Separate from `clearFilters` because it is its opposite: reset restores the default, and here
   * it is switched off — otherwise there would be no way out of results hidden by the default.
   */
  function showFinished() {
    hideFinished.value = false
    resetPage()
  }

  function clearFilters() {
    query.value = ''
    statusFilter.value = []
    priorityFilter.value = null
    searchScopes.value = { ...NO_SCOPES }
    // Hiding finished work comes back ON: it is the list's default, not an applied filter, and
    // "reset all" means returning to the usual view, not showing absolutely everything.
    hideFinished.value = true
    resetPage()
  }

  // ── Deep search ─────────────────────────────────────────────────────────────

  let deepTimer: ReturnType<typeof setTimeout> | undefined
  /** Number of the latest request: a reply to superseded input arrives later and would overwrite the fresh one. */
  let deepRun = 0

  async function runDeepSearch() {
    const needle = query.value.trim()
    const workspace = context.currentWorkspace?.code
    if (!workspace || !anyScope(searchScopes.value) || needle.length < MIN_DEEP_QUERY_LENGTH) {
      deepCodes.value = null
      return
    }
    const run = ++deepRun
    try {
      const codes = await searchTasks(
        {
          workspace,
          query: needle,
          in_brief: searchScopes.value.inBrief,
          in_plan: searchScopes.value.inPlan,
          in_journal: searchScopes.value.inJournal,
        },
        { report: false },
      )
      if (run === deepRun) deepCodes.value = new Set(codes)
    } catch {
      // A failed deep search does not blank the results: the base (title and goal) is searched
      // locally and keeps working, and the client shows a toast about the failure.
      if (run === deepRun) deepCodes.value = null
    }
  }

  /**
   * The request is debounced: deep search reads the bodies of the whole workspace, and sending it
   * on every letter would cost six requests in a row for typing one word.
   */
  function scheduleDeepSearch() {
    clearTimeout(deepTimer)
    deepTimer = setTimeout(() => void runDeepSearch(), 250)
  }

  watch([query, searchScopes], scheduleDeepSearch, { deep: true })

  // The page may have run past the end of the results: a filter narrowed the list while the person
  // was on page three.
  watch(pageCount, (count) => {
    if (page.value > count) page.value = count
  })

  // A workspace switch means a different list, not a different filter: the old cards are cleared
  // at once so that tasks from a workspace no longer selected do not stay on screen during the
  // request.
  watch(
    () => context.current,
    () => {
      groups.value = []
      items.value = []
      // Deep search codes and collapsed cards belong to the previous workspace: in the new one
      // they match nothing.
      deepCodes.value = null
      folded.value = {}
      resetPage()
      loading.value = true
      void load()
      void runDeepSearch()
    },
  )

  /**
   * Soft delete and restore — both are reversible, so there is nothing to ask here; confirmation
   * stays with the irreversible one (the task card).
   *
   * A refusal is swallowed: the client's toast has already reported it, and all that remains is to
   * re-read the list. A refusal usually means what is shown has drifted from the database, and a
   * fresh list is the answer.
   */
  async function remove(code: string) {
    try {
      await deleteTask(code)
    } catch {
      // see above
    }
    await load()
  }

  async function restore(code: string) {
    try {
      await restoreTask(code)
    } catch {
      // see above
    }
    await load()
  }

  /**
   * A group card was moved: which neighbour it now stands next to.
   *
   * The position is named by a neighbour (`after` — land below it, `before` — above it), because
   * `sort` is not visible on screen at all. The list is re-read in full, as after a task reorder:
   * the row is renumbered on the backend, and a second copy of that arithmetic here would diverge
   * from the database.
   *
   * The on-screen section order does not follow `sort` literally — empty groups go to the bottom
   * (see `sections`), so moving an empty card up is saved but does not change its place.
   */
  async function reorderGroup(code: string, place: { after?: string | null; before?: string | null }) {
    try {
      await reorderGroupRequest(code, {
        ...(place.after !== undefined ? { after_code: place.after } : {}),
        ...(place.before !== undefined ? { before_code: place.before } : {}),
      })
    } catch {
      // see below: the client's toast has already reported the refusal, and the answer is a fresh list.
    }
    await load()
  }

  // ── Task reordering: on screen at once, then in the database ─────────────────

  /** Apply a move to the store's tasks — before the backend responds (row rule: `tree.ts::moveInRow`). */
  function applyMove(code: string, afterCode: string | null, place: MovePlace) {
    const next = moveInRow(items.value, code, afterCode, place)
    if (next) items.value = next
  }

  // Reorder requests go as a CHAIN, in gesture order: otherwise two quick drops in a row would go
  // out in parallel, and the backend could apply them in reverse order.
  let moveChain: Promise<void> = Promise.resolve()
  let movesInFlight = 0

  /**
   * A row was dragged: a new place among siblings, and if it was dragged into another card or up
   * out of a branch — also a new group and a new parent.
   *
   * Order of actions: the store changes at once, the request follows, the list is re-read after
   * the response. It used to be the other way round — and for half a second the row sat in its old
   * place: the library reverts the DOM reorder before `onEnd`, and the new order appeared only
   * after the re-read. The re-read remains, but now it is reconciliation: if the backend agrees,
   * nothing changes on screen, and if not (refusal, stale list) the backend wins.
   *
   * The list is re-read once, when the chain has drained: a response to the first of two gestures
   * arriving in the middle of the second would revert the second on screen.
   */
  function reorder(
    code: string,
    afterCode: string | null,
    place: MovePlace = {},
  ): Promise<void> {
    applyMove(code, afterCode, place)
    movesInFlight += 1
    moveChain = moveChain
      .then(() =>
        reorderTask(code, {
          after_code: afterCode,
          // Key absent — field untouched; `null` — clear the group or detach from the parent. The
          // distinction is expressed by the key's presence, exactly as in the request body.
          ...('group' in place ? { group_code: place.group } : {}),
          ...('parent' in place ? { parent_code: place.parent } : {}),
        }),
      )
      .then(
        () => undefined,
        () => undefined, // the client's toast reported the refusal; the answer is the re-read below
      )
      .then(async () => {
        movesInFlight -= 1
        if (movesInFlight === 0) {
          // Reconciliation after our own reorders also covers a postponed foreign edit.
          liveReloadWaiting = false
          await load()
        }
      })
    return moveChain
  }

  // ── Live updates: foreign edits from the change feed ──────────────────────────
  // The list re-reads itself when someone else changes tasks, their positions or groups: the agent
  // via MCP, another tab. Our own echo does not reach here — the feed filters it out
  // (`stores/changes.ts`).
  //
  // The re-read WAITS while our own gesture is in progress: a row is held — swapping the list under
  // it would yank away the drop target; our own reorder is in flight — the re-read would overtake
  // its response and briefly put the row back in its old place. The postponed re-read runs once the
  // gesture ends, and the reorder chain ends with reconciliation anyway.
  let liveReloadWaiting = false

  function reloadForChanges(): void {
    if (dragging.value || movesInFlight > 0) {
      liveReloadWaiting = true
      return
    }
    liveReloadWaiting = false
    void load().then(() => {
      // Deep search codes were computed over the old bodies — a foreign edit may have changed them.
      if (query.value.trim() && anyScope(searchScopes.value)) void runDeepSearch()
    })
  }

  watch(dragging, (on) => {
    if (!on && liveReloadWaiting && movesInFlight === 0) reloadForChanges()
  })

  return {
    groups, items, loading, error, includeDeleted, format,
    query, statusFilter, priorityFilter,
    hideFinished, hideFinishedApplies, searchScopes,
    page, pageSize,
    roots, filtered, total, pageCount, pageItems,
    isEmpty, isFilteredOut, hasActiveFilters, finishedHidden, noWorkspace, sections,
    folded, isCollapsed, toggleCollapsed, dragging, lastRootOf,
    load, showDeleted, showFinished, resetPage, clearFilters, remove, restore, reorder,
    reorderGroup, reloadForChanges,
  }
})
