/**
 * API client of the tasks module (backend: /internal/workbench).
 *
 * The prefix is `/workbench`, not `/tasks`: the `/internal/tasks` root is taken by the scheduler
 * (`core_monitoring` is mounted without a prefix and holds `/tasks` and `/tasks/{module}/{code}`
 * there). While our module sat on `/tasks`, a task request — `/internal/tasks/tasks/{code}` — went
 * into its route and returned `{"error": "task not registered"}`: the detail page did not work at
 * all.
 *
 * Four surfaces: groups (topics inside a workspace), tasks, plan stages and the work journal. The
 * workspace itself lives in its own module (`features/workspace/api.ts`) — only its code goes into
 * requests from here. Group and task lists always ask about a SPECIFIC workspace: the module does
 * not read across workspaces, and `workspace` is mandatory for them.
 *
 * Codes arrive prefixed (TASKGROUP@…, TASK@…, STAGE@…, NOTE@…, WORKSPACE@…) and go back the same way:
 * the backend strips the prefix itself, and in a URL segment the code is encoded with
 * `encodeURIComponent` — "@" is allowed in a path, but encoding is safer for any future forms.
 *
 * Dates are in SQL format (dto.py::DatetimeUTCStr), formatted by shared/utils/date.
 */

import { internalApi, type RequestOptions } from '@/api/client/internal'

const BASE = '/workbench'

const seg = (code: string) => encodeURIComponent(code)

// ── Groups ────────────────────────────────────────────────────────────────────

/**
 * A group is a long-lived topic inside a workspace (billing, interface, infrastructure). The task
 * list draws section headings from them, and they are created and edited on their own page — the
 * same set of endpoints as for a workspace, with one exception: a group's workspace is set at
 * creation and cannot be changed by an edit, otherwise moving a group would drag all its tasks
 * along.
 */
export interface GroupRow {
  code: string
  workspace_code: string
  title: string
  description: string
  /** A name from the `shared/colors.ts` registry; empty — no color chosen. */
  color: string
  /** A name from the `shared/icons.ts` registry; empty — no icon chosen. */
  icon: string
  /** Higher `sort` — higher in the list. */
  sort: number
  created_at: string
  updated_at: string
  deleted_at: string | null
}

/** A group list row: the card plus how many live tasks are inside. */
export interface GroupListRow extends GroupRow {
  task_count: number
}

export interface GroupBody {
  title: string
  description: string
  color: string
  icon: string
  /** Position among siblings: higher `sort` — higher up. */
  sort: number
}

export interface ListGroupsParams {
  /** Workspace code — mandatory: a group does not exist outside a workspace. */
  workspace: string
  include_deleted?: boolean
}

export async function listGroups(
  params: ListGroupsParams,
  opts?: RequestOptions,
): Promise<GroupListRow[]> {
  return internalApi.get<GroupListRow[]>(`${BASE}/groups`, { ...opts, query: { ...params } })
}

export async function getGroup(code: string, opts?: RequestOptions): Promise<GroupRow> {
  return internalApi.get<GroupRow>(`${BASE}/groups/${seg(code)}`, opts)
}

/** The workspace goes as a query parameter, not in the body: an update does not accept it at all. */
export async function createGroup(
  workspace: string,
  body: GroupBody,
  opts?: RequestOptions,
): Promise<GroupRow> {
  return internalApi.post<GroupRow>(`${BASE}/groups`, body, { ...opts, query: { workspace } })
}

export async function updateGroup(
  code: string,
  body: GroupBody,
  opts?: RequestOptions,
): Promise<GroupRow> {
  return internalApi.put<GroupRow>(`${BASE}/groups/${seg(code)}`, body, opts)
}

/**
 * Dragging a group card: the neighbour it landed relative to.
 *
 * Exactly one of the two reference points — the backend accepts neither both at once nor none:
 * "move it somewhere" is not a position. There is no number here on purpose; the person does not
 * see `sort` on screen.
 */
export async function reorderGroup(
  code: string,
  body: { after_code?: string | null; before_code?: string | null },
  opts?: RequestOptions,
): Promise<GroupRow> {
  return internalApi.post<GroupRow>(`${BASE}/groups/${seg(code)}/reorder`, body, opts)
}

/** What becomes of a group's tasks when it is deleted — mirrors `constants.GROUP_TASK_DISPOSALS`. */
export type GroupTaskDisposal = 'ungroup' | 'move' | 'delete'

/**
 * Soft delete together with the fate of the group's tasks, in one transaction on the backend.
 * `tasks` is required while the group holds live tasks (409 `tasks.group.has_tasks` without it);
 * `target` is the group to move them to. `restoreGroup` later brings back the group alone.
 */
export async function deleteGroup(
  code: string,
  fate: { tasks?: GroupTaskDisposal; target?: string } = {},
  opts?: RequestOptions,
): Promise<void> {
  await internalApi.del<void>(`${BASE}/groups/${seg(code)}`, undefined, {
    ...opts,
    query: { ...opts?.query, ...fate },
  })
}

export async function restoreGroup(code: string, opts?: RequestOptions): Promise<GroupRow> {
  return internalApi.post<GroupRow>(`${BASE}/groups/${seg(code)}/restore`, undefined, opts)
}

/** Physical deletion of a group: its tasks survive and move to the "No group" section. */
export async function purgeGroup(code: string, opts?: RequestOptions): Promise<void> {
  await internalApi.del<void>(`${BASE}/groups/${seg(code)}/purge`, undefined, opts)
}

// ── Tasks ─────────────────────────────────────────────────────────────────────

/** The task's own fields — everything in its row except the brief and the plan. */
export interface TaskRow {
  code: string
  workspace_code: string
  /** Group (`TASKGROUP@…`) or `null` — the task is outside groups, its place is the "No group" section. */
  group_code: string | null
  /** `simple` | `standard` | `extended` — depth of tracking, see `labels.ts`. */
  type: string
  status: string
  priority: string
  title: string
  /** Goal: what becomes true once the work is done. */
  description: string
  /** `human` | `agent` — who created the row. */
  created_by: string
  /** Deadline — the only date assignable to a task. */
  deadline_at: string | null
  started_at: string | null
  completed_at: string | null
  canceled_at: string | null
  created_at: string
  updated_at: string
  /** Not null — the task is in the trash: editing is unavailable, restore and purge are. */
  deleted_at: string | null
}

/** A list row: the task card plus its place in the tree. */
export interface TaskListRow extends TaskRow {
  /** Parent (`TASK@…`) or `null` — a workspace root. */
  parent_code: string | null
  /** Position among siblings: higher `sort` — higher up. */
  sort: number
  /** The task has tasks under it — the list draws a mark from this rather than expanding the branch. */
  has_children: boolean
}

/** A plan stage: a step of work with its own state and evidence of completion. */
export interface StageRow {
  code: string
  task_code: string
  /** The number grows downward: the first stage is one. */
  number: number
  status: string
  title: string
  description: string
  body: string
  /** A pointer to the evidence: a command and its result, a path, a diff. Without it the stage cannot close. */
  evidence: string
  started_at: string | null
  finished_at: string | null
  created_at: string
  updated_at: string
}

export interface StageBody {
  title: string
  description: string
  body: string
  evidence: string
  /** Omitted — the stage becomes the next in sequence. */
  number?: number | null
}

/**
 * A journal entry: the subject (`title` + `body`) and a resolution. Empty `resolution` — the
 * entry is open.
 *
 * `type`: `decision` (a choice made along the way), `remark` (the task author's remark), `finding`
 * (something found outside the task), `fact` (something to remember). A fact is closed when
 * written.
 */
export interface NoteRow {
  code: string
  task_code: string
  stage_code: string | null
  type: string
  title: string
  body: string
  resolution: string
  created_at: string
}

export interface NoteBody {
  type: string
  title: string
  body: string
  resolution?: string
  stage_code?: string | null
}

/**
 * The whole task. Group and parent arrive as rows, not bare codes: the page shows them by name,
 * and there is no point fetching the names with two extra requests on every open. Stages and the
 * journal come along too — the task detail is the work screen.
 */
export interface TaskDetail extends TaskListRow {
  /** Details and starting requirements; markdown. */
  context: string
  /** What is allowed and what is not; a markdown list. */
  constraints: string
  /** Requirements for the delivery format and for stages; a markdown list. */
  criteria: string
  /** The agent's plan; markdown. */
  body: string
  group: GroupRow | null
  parent: TaskListRow | null
  children: TaskListRow[]
  stages: StageRow[]
  notes: NoteRow[]
}

export interface TaskCreateBody {
  workspace: string
  title: string
  description?: string
  context?: string
  constraints?: string
  criteria?: string
  body?: string
  type?: string
  status?: string
  priority?: string
  group_code?: string | null
  parent_code?: string | null
  deadline_at?: string | null
}

/**
 * An update is a full replacement of the card: the backend erases any field not sent. So the form
 * always sends all fields, not only the changed ones, otherwise there would be no way to clear a
 * group or a deadline.
 *
 * Status is absent on purpose: it is changed by `setTaskStatus` — only that path stamps the start,
 * completion and cancel timestamps.
 */
export interface TaskUpdateBody {
  title: string
  description: string
  context: string
  constraints: string
  criteria: string
  body: string
  type: string
  priority: string
  group_code: string | null
  deadline_at: string | null
}

export interface ListTasksParams {
  workspace: string
  include_deleted?: boolean
  status?: string
  /** Group code; empty string — only tasks outside groups (the "No group" section). */
  group?: string
}

export async function listTasks(
  params: ListTasksParams,
  opts?: RequestOptions,
): Promise<TaskListRow[]> {
  return internalApi.get<TaskListRow[]>(`${BASE}/tasks`, { ...opts, query: { ...params } })
}

/**
 * Deep search scopes: what, besides title and goal, goes into the haystack.
 *
 * None is on by default — neither here nor on the backend: a search that quietly digs into
 * eight-kilobyte bodies returns matches that do not tell whether it is the right task.
 */
export interface SearchTasksParams {
  workspace: string
  query: string
  /** The brief: context, constraints, criteria. */
  in_brief?: boolean
  /** The task plan and its stage bodies. */
  in_plan?: boolean
  /** Journal entries. */
  in_journal?: boolean
}

/**
 * Codes of tasks whose BODIES matched the query — the second half of the list search.
 *
 * Title and goal are in every row, and the list searches them itself — instantly and without a
 * network round trip. This endpoint is only for what the row lacks, hence the answer is just codes:
 * the caller already has the cards and intersects them with its list.
 */
export async function searchTasks(
  params: SearchTasksParams,
  opts?: RequestOptions,
): Promise<string[]> {
  return internalApi.get<string[]>(`${BASE}/tasks/search`, { ...opts, query: { ...params } })
}

export async function getTask(code: string, opts?: RequestOptions): Promise<TaskDetail> {
  return internalApi.get<TaskDetail>(`${BASE}/tasks/${seg(code)}`, opts)
}

export async function createTask(
  body: TaskCreateBody,
  opts?: RequestOptions,
): Promise<TaskDetail> {
  return internalApi.post<TaskDetail>(`${BASE}/tasks`, body, opts)
}

export async function updateTask(
  code: string,
  body: TaskUpdateBody,
  opts?: RequestOptions,
): Promise<TaskDetail> {
  return internalApi.put<TaskDetail>(`${BASE}/tasks/${seg(code)}`, body, opts)
}

/**
 * Partial update: only the named fields are sent, the rest stay untouched on the backend. This way
 * the task page, saving one field, does not roll back what the agent wrote meanwhile. `null` for
 * group and deadline clears them.
 */
export async function patchTask(
  code: string,
  body: Partial<TaskUpdateBody>,
  opts?: RequestOptions,
): Promise<TaskDetail> {
  return internalApi.patch<TaskDetail>(`${BASE}/tasks/${seg(code)}`, body, opts)
}

/** Status change has its own endpoint: together with the status the backend stamps the phase. */
export async function setTaskStatus(
  code: string,
  status: string,
  opts?: RequestOptions,
): Promise<TaskDetail> {
  return internalApi.post<TaskDetail>(`${BASE}/tasks/${seg(code)}/status`, { status }, opts)
}

/** Moving a branch: the new parent (`null` — root) and the position among siblings. */
export async function moveTask(
  code: string,
  body: { parent_code: string | null; sort?: number | null },
  opts?: RequestOptions,
): Promise<TaskDetail> {
  return internalApi.post<TaskDetail>(`${BASE}/tasks/${seg(code)}/move`, body, opts)
}

/**
 * Dragging a list row: which task it landed after and, if it was dragged into another card, which
 * group it is in now.
 *
 * The position is named by a NEIGHBOUR, not a number: the on-screen list has its own filters and
 * pages, and a row's number there does not match its number among siblings in the database.
 * `after_code: null` — to the start of the row.
 *
 * `group_code` key absent — the group is untouched, `null` — it is cleared: reordering within its
 * own card must know nothing about groups, while a move into "No group" must be able to clear it.
 *
 * `parent_code` works the same way: key absent — the parent is untouched, `null` — detach. This
 * expresses the list's second gesture: a subtask was pulled out of a branch and became a regular
 * task.
 */
export async function reorderTask(
  code: string,
  body: {
    after_code: string | null
    group_code?: string | null
    parent_code?: string | null
  },
  opts?: RequestOptions,
): Promise<TaskDetail> {
  return internalApi.post<TaskDetail>(`${BASE}/tasks/${seg(code)}/reorder`, body, opts)
}

/** Soft delete — together with the whole branch under the task; `restoreTask` brings it back. */
export async function deleteTask(code: string, opts?: RequestOptions): Promise<void> {
  await internalApi.del<void>(`${BASE}/tasks/${seg(code)}`, undefined, opts)
}

export async function restoreTask(code: string, opts?: RequestOptions): Promise<TaskDetail> {
  return internalApi.post<TaskDetail>(`${BASE}/tasks/${seg(code)}/restore`, undefined, opts)
}

/** Physical deletion of a task with its branch: there will be nothing to restore. */
export async function purgeTask(code: string, opts?: RequestOptions): Promise<void> {
  await internalApi.del<void>(`${BASE}/tasks/${seg(code)}/purge`, undefined, opts)
}

// ── Plan stages ───────────────────────────────────────────────────────────────

export async function listStages(
  taskCode: string,
  opts?: RequestOptions,
): Promise<StageRow[]> {
  return internalApi.get<StageRow[]>(`${BASE}/tasks/${seg(taskCode)}/stages`, opts)
}

export async function createStage(
  taskCode: string,
  body: Omit<StageBody, 'evidence'> & { evidence?: string },
  opts?: RequestOptions,
): Promise<StageRow> {
  return internalApi.post<StageRow>(`${BASE}/tasks/${seg(taskCode)}/stages`, body, opts)
}

export async function updateStage(
  code: string,
  body: StageBody,
  opts?: RequestOptions,
): Promise<StageRow> {
  return internalApi.put<StageRow>(`${BASE}/stages/${seg(code)}`, body, opts)
}

/** Closing a stage: the backend rejects `done` with empty `evidence` — that is the gate. */
export async function setStageStatus(
  code: string,
  status: string,
  opts?: RequestOptions,
): Promise<StageRow> {
  return internalApi.post<StageRow>(`${BASE}/stages/${seg(code)}/status`, { status }, opts)
}

export async function deleteStage(code: string, opts?: RequestOptions): Promise<void> {
  await internalApi.del<void>(`${BASE}/stages/${seg(code)}`, undefined, opts)
}

// ── Journal ───────────────────────────────────────────────────────────────────

export interface ListNotesParams {
  type?: string
  open_only?: boolean
}

export async function listNotes(
  taskCode: string,
  params?: ListNotesParams,
  opts?: RequestOptions,
): Promise<NoteRow[]> {
  return internalApi.get<NoteRow[]>(`${BASE}/tasks/${seg(taskCode)}/notes`, {
    ...opts,
    query: { ...params },
  })
}

export async function createNote(
  taskCode: string,
  body: NoteBody,
  opts?: RequestOptions,
): Promise<NoteRow> {
  return internalApi.post<NoteRow>(`${BASE}/tasks/${seg(taskCode)}/notes`, body, opts)
}

/** Close an entry. The backend rejects a repeated close: the journal is append-only. */
export async function resolveNote(
  code: string,
  resolution: string,
  opts?: RequestOptions,
): Promise<NoteRow> {
  return internalApi.post<NoteRow>(`${BASE}/notes/${seg(code)}/resolve`, { resolution }, opts)
}

export async function deleteNote(code: string, opts?: RequestOptions): Promise<void> {
  await internalApi.del<void>(`${BASE}/notes/${seg(code)}`, undefined, opts)
}
