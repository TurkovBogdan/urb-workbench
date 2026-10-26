// Lookup client (backend: /internal/core/lookup). What an entity code stands for — for codes of
// any module, in one request. The shape is a contract with `core_lookup/dto.py`.
//
// Silent (`report: false`): previews are fetched in the background for whatever a body quotes,
// and a toast per failed batch would land on a person who asked for nothing.
import { internalApi } from '@/api/client/internal'

/** Why a code has no preview. Values are a contract with `core_lookup/registry.py::Miss`. */
export type PreviewMiss = 'not_found' | 'foreign_scope' | 'deleted' | 'failed'

export interface PreviewRecord {
  code: string
  title: string
  description: string
  /** App path of the entity's page, without the host; empty on an error. */
  link: string
  /** A stored file's type (`application/pdf`); empty for every other code. */
  mime: string
  /** The page's holder holds the file: the title and description are its own to edit. */
  held: boolean
  error: { code: PreviewMiss; message: string } | null
}

/** The most codes one request may carry; the backend refuses a longer batch whole. */
export const PREVIEW_BATCH_MAX = 200

/**
 * @param workspace the workspace the codes are read in (`WORKSPACE@…`)
 * @param holder the entity whose page shows them (`TASK@…`, `CODEX@…`): a file is named as that
 *   entity names it
 */
export function fetchPreviews(
  codes: string[],
  workspace: string | null,
  holder: string | null = null,
): Promise<PreviewRecord[]> {
  return internalApi.post<PreviewRecord[]>(
    '/core/lookup/preview',
    holder ? { codes, workspace, holder } : { codes, workspace },
    { report: false },
  )
}
