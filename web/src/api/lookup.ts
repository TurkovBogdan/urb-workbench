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
  error: { code: PreviewMiss; message: string } | null
}

/** The most codes one request may carry; the backend refuses a longer batch whole. */
export const PREVIEW_BATCH_MAX = 200

export function fetchPreviews(codes: string[], workspace: string | null): Promise<PreviewRecord[]> {
  return internalApi.post<PreviewRecord[]>(
    '/core/lookup/preview',
    { codes, workspace },
    { report: false },
  )
}
