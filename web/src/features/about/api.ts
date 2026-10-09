/**
 * Client for the "About" section (backend: /internal/core/update).
 *
 * Three calls with different costs: `installation` reads local facts and answers instantly, `check`
 * goes to the remote (POST, because it changes the checkout's tracking refs, and may take seconds),
 * `start` hands the installation over to the update script and answers BEFORE the backend goes
 * down.
 *
 * Everything unknown arrives as `null`: without a `.git` directory the installation knows neither
 * the commit nor whether the tree is clean, and a branch without a manifest has no version. A zero
 * in that place would be a claim.
 */

import { internalApi } from '@/api/client/internal'

const BASE = '/core/update'

/** What is installed here: the release, the build on top of it, and why an update would refuse. */
export interface Installation {
  version: string | null
  release_date: string | null
  /** The branch the installation follows (`UPDATE_BRANCH`). */
  followed_branch: string
  checked_out_branch: string | null
  branch_matches: boolean
  commit: string | null
  /** `git describe`: the release, the distance from it and the build in one line. */
  describes_as: string | null
  dirty: boolean | null
  /** Code of the reason an update would refuse to run (`about.refusal.*`), or `null`. */
  refusal: 'dirty_tree' | 'branch_mismatch' | 'platform_unsupported' | null
}

/** What the branch offers and where we stand relative to it. */
export interface UpstreamHead {
  branch: string
  version: string | null
  commit: string
  behind: number | null
  /** Local commits missing from the remote: a fast-forward will break on them. */
  ahead: number | null
}

export interface StartedUpdate {
  status: string
  pid: number
  log: string
}

export const updateApi = {
  installation: () => internalApi.get<Installation>(BASE),
  check: () => internalApi.post<UpstreamHead>(`${BASE}/check`),
  start: () => internalApi.post<StartedUpdate>(`${BASE}/start`),
}
