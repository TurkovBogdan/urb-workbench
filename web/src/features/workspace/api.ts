/**
 * API client of the workspace module (backend: /internal/workspace).
 *
 * A workspace is the top level of data isolation: the modules on top (tasks today, documentation
 * tomorrow) narrow their lists to what is selected in the sidebar. That is why both the module
 * and this folder stand apart from them: the dependency goes bottom-up and only one way.
 *
 * Codes arrive prefixed (WORKSPACE@…) and are sent back the same way: the backend strips the
 * prefix itself, and in a path segment the code is encoded with `encodeURIComponent` — "@" is
 * allowed in a path, but encoding is safer for any future code shapes.
 *
 * Dates are in SQL format (dto.py::DatetimeUTCStr), formatted by shared/utils/date.
 */

import { internalApi, type RequestOptions } from '@/api/client/internal'

const BASE = '/workspace'

const seg = (code: string) => encodeURIComponent(code)

export interface WorkspaceRow {
  code: string
  title: string
  description: string
  /** A name from the `shared/colors.ts` registry; empty — no colour chosen, render with the accent. */
  color: string
  /** A name from the `shared/icons.ts` registry; empty — no icon chosen, render the fallback. */
  icon: string
  /** Position in the list: higher `sort` — higher up. */
  sort: number
  created_at: string
  updated_at: string
  /** Not null — the workspace is in the trash: no editing, only restore and purge. */
  deleted_at: string | null
}

/**
 * A content counter: whose it is, how to label it and what it counted.
 *
 * The set of counters is not fixed — the modules on top declare it (`workspace.stats` on the
 * backend), and it depends on the app's composition. The label arrives as a message KEY: it is
 * owned by the module the entity belongs to, and the text lives in its dictionary, not ours.
 */
export interface WorkspaceCounter {
  key: string
  label_key: string
  count: number
}

export interface WorkspaceListRow extends WorkspaceRow {
  counters: WorkspaceCounter[]
}

export interface WorkspaceBody {
  title: string
  description: string
  color: string
  icon: string
  sort: number
}

export interface ListWorkspacesParams {
  /** Show deleted ones too — the toggle in the list header. */
  include_deleted?: boolean
}

export async function listWorkspaces(
  params: ListWorkspacesParams = {},
  opts?: RequestOptions,
): Promise<WorkspaceListRow[]> {
  return internalApi.get<WorkspaceListRow[]>(BASE, { ...opts, query: { ...params } })
}

export async function getWorkspace(
  code: string,
  opts?: RequestOptions,
): Promise<WorkspaceRow> {
  return internalApi.get<WorkspaceRow>(`${BASE}/${seg(code)}`, opts)
}

export async function createWorkspace(
  body: WorkspaceBody,
  opts?: RequestOptions,
): Promise<WorkspaceRow> {
  return internalApi.post<WorkspaceRow>(BASE, body, opts)
}

export async function updateWorkspace(
  code: string,
  body: WorkspaceBody,
  opts?: RequestOptions,
): Promise<WorkspaceRow> {
  return internalApi.put<WorkspaceRow>(`${BASE}/${seg(code)}`, body, opts)
}

/**
 * Move a workspace next to another one — exactly one of `after_code` (land below it) and
 * `before_code` (land above it). The position is a neighbour, not a number: the person never sees
 * `sort`, only which rows the dragged one landed between.
 */
export async function reorderWorkspace(
  code: string,
  body: { after_code?: string; before_code?: string },
  opts?: RequestOptions,
): Promise<WorkspaceRow> {
  return internalApi.post<WorkspaceRow>(`${BASE}/${seg(code)}/reorder`, body, opts)
}

/** Soft delete: the content stays, it can be brought back with `restoreWorkspace`. */
export async function deleteWorkspace(code: string, opts?: RequestOptions): Promise<void> {
  await internalApi.del<void>(`${BASE}/${seg(code)}`, undefined, opts)
}

export async function restoreWorkspace(
  code: string,
  opts?: RequestOptions,
): Promise<WorkspaceRow> {
  return internalApi.post<WorkspaceRow>(`${BASE}/${seg(code)}/restore`, undefined, opts)
}

/**
 * Hard delete: the workspace disappears together with everything the modules on top kept in it —
 * there is nothing to bring back. A separate function, not a flag on `deleteWorkspace`, exactly as
 * on the backend: the irreversible must not differ from the reversible by one argument at the call
 * site.
 */
export async function purgeWorkspace(code: string, opts?: RequestOptions): Promise<void> {
  await internalApi.del<void>(`${BASE}/${seg(code)}/purge`, undefined, opts)
}
