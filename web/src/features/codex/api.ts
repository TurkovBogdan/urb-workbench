/**
 * API client of the codex module (backend: /internal/codex).
 *
 * A codex is shared: it belongs to no workspace and is mounted into several. So the codexes
 * themselves are read without a workspace, and the mounts and the canvas tree — through the
 * current one (`features/workspace/stores/workspace-context.store`).
 *
 * Codes arrive prefixed (CODEX@…) and are sent back the same way. A codex and a codex note share
 * the prefix, which is why the editor lives at one address for both.
 */

import { internalApi, internalUpload, internalUrl, type RequestOptions } from '@/api/client/internal'
import { uploadFile, type UploadOptions } from '@/api/upload'
import type { TransferChoice, TransferPlanBase, TransferRecoded, TransferUpload } from '@/components/transfer/types'

const BASE = '/codex'

const seg = (code: string) => encodeURIComponent(code)

export interface CodexRow {
  code: string
  segment: string
  title: string
  /** When to turn to the codex — the line the agent picks it by. */
  description: string
  /** Names from `shared/colors.ts` / `shared/icons.ts`; empty — not chosen. */
  color: string
  icon: string
  sort: number
  /** In how many live workspaces it is mounted — an edit is seen in all of them. */
  mount_count: number
  created_at: string
  updated_at: string
  deleted_at: string | null
}

/** A codex whole: with its rules — what `codex_rules` hands the agent. */
export interface CodexDetail extends CodexRow {
  body: string
}

export interface CodexBody {
  segment: string
  title: string
  description: string
  body: string
  /** Left out — the look stays as it is: the material page saves the text only. */
  color?: string
  icon?: string
}

export interface CodexNote {
  code: string
  codex_code: string
  /** The parent note; `null` — the codex's top level. */
  parent_code: string | null
  segment: string
  title: string
  description: string
  body: string
  sort: number
  /** `python/test/fixtures`; empty for a deleted note. */
  path: string
  created_at: string
  updated_at: string
  deleted_at: string | null
}

export interface CodexNoteBody {
  segment: string
  title: string
  description: string
  body: string
}

export interface TreeNode {
  code: string
  segment: string
  title: string
  description: string
  /** The codex's look on its root; empty on a note. */
  color: string
  icon: string
  path: string
  /** A deleted note — only in a tree read with its deleted notes; a codex never is. */
  deleted: boolean
  children: TreeNode[]
}

export interface MountRow {
  codex: CodexRow
  workspace_code: string
  sort: number
  agent_can_edit: boolean
  created_at: string
}

// ── codexes ───────────────────────────────────────────────────────────────────

export function listCodexes(includeDeleted = false, opts?: RequestOptions): Promise<CodexRow[]> {
  return internalApi.get<CodexRow[]>(`${BASE}/codexes`, {
    ...opts,
    query: { include_deleted: includeDeleted },
  })
}

export function getCodex(code: string, opts?: RequestOptions): Promise<CodexDetail> {
  return internalApi.get<CodexDetail>(`${BASE}/codexes/${seg(code)}`, opts)
}

export function createCodex(body: CodexBody, opts?: RequestOptions): Promise<CodexDetail> {
  return internalApi.post<CodexDetail>(`${BASE}/codexes`, body, opts)
}

export function updateCodex(code: string, body: CodexBody, opts?: RequestOptions): Promise<CodexDetail> {
  return internalApi.put<CodexDetail>(`${BASE}/codexes/${seg(code)}`, body, opts)
}

export async function deleteCodex(code: string, opts?: RequestOptions): Promise<void> {
  await internalApi.del<void>(`${BASE}/codexes/${seg(code)}`, undefined, opts)
}

export function restoreCodex(code: string, opts?: RequestOptions): Promise<CodexDetail> {
  return internalApi.post<CodexDetail>(`${BASE}/codexes/${seg(code)}/restore`, undefined, opts)
}

// ── notes ─────────────────────────────────────────────────────────────────────

export function getNote(code: string, opts?: RequestOptions): Promise<CodexNote> {
  return internalApi.get<CodexNote>(`${BASE}/notes/${seg(code)}`, opts)
}

export function createNote(
  body: CodexNoteBody & { parent_code: string },
  opts?: RequestOptions,
): Promise<CodexNote> {
  return internalApi.post<CodexNote>(`${BASE}/notes`, body, opts)
}

export function updateNote(code: string, body: CodexNoteBody, opts?: RequestOptions): Promise<CodexNote> {
  return internalApi.put<CodexNote>(`${BASE}/notes/${seg(code)}`, body, opts)
}

/**
 * Move and place: `parent_code` — under that codex (its top level) or note; `after_code` — right
 * after that sibling, `null` — first. A key left out keeps its value.
 */
export function moveNote(
  code: string,
  body: { parent_code?: string; after_code?: string | null },
  opts?: RequestOptions,
): Promise<CodexNote> {
  return internalApi.post<CodexNote>(`${BASE}/notes/${seg(code)}/move`, body, opts)
}

/** The codex's deleted notes — each deletion once, by the note it started at. */
export function codexTrash(code: string, opts?: RequestOptions): Promise<CodexNote[]> {
  return internalApi.get<CodexNote[]>(`${BASE}/codexes/${seg(code)}/trash`, opts)
}

/** Bring a deleted note back with the branch that left with it. */
export function restoreNote(code: string, opts?: RequestOptions): Promise<CodexNote> {
  return internalApi.post<CodexNote>(`${BASE}/notes/${seg(code)}/restore`, undefined, opts)
}

/** Soft. A note with children goes only with `branch` — otherwise 409 `codex.note.has_children`. */
export async function deleteNote(code: string, branch = false, opts?: RequestOptions): Promise<void> {
  await internalApi.del<void>(`${BASE}/notes/${seg(code)}`, undefined, {
    ...opts,
    query: { branch },
  })
}

// ── a note's files ────────────────────────────────────────────────────────────
// Only a note holds files; the code of a codex is refused (`codex.file.holder_is_codex`).

export interface NoteFileRow {
  /** `FILE@…` */
  code: string
  note_code: string
  /** Empty — the file goes by `original_filename + original_extension`. */
  title: string
  description: string
  original_filename: string
  original_extension: string
  mime: string
  /** `core_storage`'s kind of file: `image`, `document`, … */
  type: string
  size: number
  sort: number
  created_at: string
  updated_at: string
}

export function listNoteFiles(note: string, opts?: RequestOptions): Promise<NoteFileRow[]> {
  return internalApi.get<NoteFileRow[]>(`${BASE}/notes/${seg(note)}/files`, opts)
}

/**
 * Send one file into the note, at the end of its files — through the file upload module, the note
 * named by its `CODEX@` code. The body is the file itself; a refusal is an `ApiError` the caller
 * shows — `codex.file.already_attached` carries the file the note holds (`params.file`,
 * `params.name`, `params.type`), `core_storage_upload.file.too_large` the ceiling.
 */
export function uploadNoteFile(
  note: string,
  file: File,
  opts: Omit<UploadOptions, 'query'> = {},
): Promise<NoteFileRow> {
  return uploadFile<NoteFileRow>(note.includes('@') ? note : `CODEX@${note}`, file, opts)
}

/** The whole order, top to bottom, as the person left it. */
export function reorderNoteFiles(note: string, codes: string[], opts?: RequestOptions): Promise<NoteFileRow[]> {
  return internalApi.put<NoteFileRow[]>(`${BASE}/notes/${seg(note)}/files/order`, { codes }, opts)
}

/** What the note calls the file and says is in it; a field left out stays as it is. */
export function updateNoteFile(
  note: string,
  file: string,
  body: { title?: string; description?: string },
  opts?: RequestOptions,
): Promise<NoteFileRow> {
  return internalApi.patch<NoteFileRow>(`${BASE}/notes/${seg(note)}/files/${seg(file)}`, body, opts)
}

/** Take the file out of the note; the file itself goes once nothing else holds it. */
export async function detachNoteFile(note: string, file: string, opts?: RequestOptions): Promise<void> {
  await internalApi.del<void>(`${BASE}/notes/${seg(note)}/files/${seg(file)}`, undefined, opts)
}

// ── the workspace's canvas ────────────────────────────────────────────────────

export function listMounts(workspace: string, opts?: RequestOptions): Promise<MountRow[]> {
  return internalApi.get<MountRow[]>(`${BASE}/workspaces/${seg(workspace)}/mounts`, opts)
}

export function canvasTree(
  workspace: string,
  includeDeleted = false,
  opts?: RequestOptions,
): Promise<TreeNode[]> {
  return internalApi.get<TreeNode[]>(`${BASE}/workspaces/${seg(workspace)}/tree`, {
    ...opts,
    query: { include_deleted: includeDeleted },
  })
}

/** Codes of the canvas records whose title, description or text holds the query — any case. */
export function searchCanvas(workspace: string, query: string, opts?: RequestOptions): Promise<string[]> {
  return internalApi.get<string[]>(`${BASE}/workspaces/${seg(workspace)}/search`, {
    ...opts,
    query: { query },
  })
}

export function mount(workspace: string, codexCode: string, opts?: RequestOptions): Promise<MountRow> {
  return internalApi.post<MountRow>(
    `${BASE}/workspaces/${seg(workspace)}/mounts`,
    { codex_code: codexCode },
    opts,
  )
}

export async function unmount(workspace: string, codexCode: string, opts?: RequestOptions): Promise<void> {
  await internalApi.del<void>(
    `${BASE}/workspaces/${seg(workspace)}/mounts/${seg(codexCode)}`,
    undefined,
    opts,
  )
}

export function setAgentCanEdit(
  workspace: string,
  codexCode: string,
  value: boolean,
  opts?: RequestOptions,
): Promise<MountRow> {
  return internalApi.patch<MountRow>(
    `${BASE}/workspaces/${seg(workspace)}/mounts/${seg(codexCode)}`,
    { agent_can_edit: value },
    opts,
  )
}

/** A codex as the workspace orders it — switched on there or not. */
export interface WorkspaceCodexRow {
  codex: CodexRow
  mounted: boolean
  /** False while switched off. */
  agent_can_edit: boolean
}

/** Every codex in the workspace's order — the same for the switched-on and the switched-off. */
export function listWorkspaceCodexes(
  workspace: string,
  includeDeleted = false,
  opts?: RequestOptions,
): Promise<WorkspaceCodexRow[]> {
  return internalApi.get<WorkspaceCodexRow[]>(`${BASE}/workspaces/${seg(workspace)}/codexes`, {
    ...opts,
    query: { include_deleted: includeDeleted },
  })
}

/** Place a codex right after `afterCode` in the workspace's order; `null` — at the top. */
export function reorderWorkspaceCodex(
  workspace: string,
  codexCode: string,
  afterCode: string | null,
  opts?: RequestOptions,
): Promise<WorkspaceCodexRow[]> {
  return internalApi.post<WorkspaceCodexRow[]>(
    `${BASE}/workspaces/${seg(workspace)}/codexes/${seg(codexCode)}/reorder`,
    { after_code: afterCode },
    opts,
  )
}

// ── Transfer between installations (.ucdx) ────────────────────────────────────
// The export is fetched by the browser itself: the answer is a file named by the server.

/** Where the browser downloads a codex's archive from — the whole codex, its bin included. */
export function codexExportUrl(code: string): string {
  return internalUrl(`${BASE}/codexes/${seg(code)}/export`)
}

// Reading and applying go through the whole archive — every record and every file.
const TRANSFER_TIMEOUT_MS = 10 * 60 * 1000

export interface CodexImportPlan extends TransferPlanBase {
  root: { code: string; title: string; path: string; deleted: boolean }
  counts: { notes: number; deleted_notes: number; files: number }
  notices: TransferPlanBase['notices'] & { repathed: TransferRecoded[] }
}

export interface CodexImportReport {
  codex: { code: string; title: string; segment: string }
  mounted: boolean
  counts: { created: Record<string, number>; updated: Record<string, number> }
  recoded: TransferRecoded[]
  repathed: (TransferRecoded & { code?: string })[]
  /** Records here that went to the bin with a parent the archive brought in the bin. */
  binned: { code: string; title: string }[]
  truncated: { entity: string; code: string; field: string }[]
  refs_rewritten: number
  dangling_refs: string[]
}

export function uploadCodexArchive(
  file: File,
  onProgress: (loaded: number, total: number) => void,
  signal?: AbortSignal,
): Promise<TransferUpload> {
  return internalUpload<TransferUpload>(`${BASE}/transfer/upload`, file, {
    query: { filename: file.name },
    onProgress,
    signal,
  })
}

export function analyzeCodexImport(uploadId: string): Promise<CodexImportPlan> {
  return internalApi.post<CodexImportPlan>(`${BASE}/transfer/${seg(uploadId)}/analyze`, {}, {
    report: false,
    timeoutMs: TRANSFER_TIMEOUT_MS,
  })
}

export function applyCodexImport(
  uploadId: string,
  body: { workspace: string | null; decisions: Record<string, TransferChoice>; plan_token: string },
): Promise<CodexImportReport> {
  return internalApi.post<CodexImportReport>(`${BASE}/transfer/${seg(uploadId)}/apply`, body, {
    report: false,
    timeoutMs: TRANSFER_TIMEOUT_MS,
  })
}

/** Give the uploaded archive back without importing it. */
export async function cancelCodexImport(uploadId: string): Promise<void> {
  await internalApi.del<void>(`${BASE}/transfer/${seg(uploadId)}`, undefined, { report: false })
}
