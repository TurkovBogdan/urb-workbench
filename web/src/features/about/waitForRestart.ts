/**
 * Waiting for a restart: first the backend must disappear, and only then answer again.
 *
 * Waiting for "answered" alone won't do: seconds pass between the reply to the start call and the
 * processes stopping (`uv run`, polling the remote), and the poll would hit the still-alive OLD
 * backend — the page would reload only to fall over with it a moment later.
 *
 * The API client is no good here: its failures during this time are the normal course of events,
 * not errors worth showing. Hence a bare `fetch` that silently swallows failures.
 */

const HEALTH_URL = `${import.meta.env.VITE_API_BASE ?? ''}/internal/health`

const POLL_INTERVAL_MS = 2000
/** How long to wait for it to go away. If it doesn't, the command refused without touching processes. */
const DISAPPEARANCE_BUDGET_MS = 90 * 1000
/** The full sequence: stop, sync, database copy, migrations, start. */
const RETURN_BUDGET_MS = 15 * 60 * 1000

export async function waitForRestart(): Promise<boolean> {
  const wentDown = await waitUntil(() => backendIsServing().then((up) => !up), DISAPPEARANCE_BUDGET_MS)
  if (!wentDown) return false

  return waitUntil(backendIsServing, RETURN_BUDGET_MS)
}

/** "Alive" means `ok`: a degraded backend answers 200 with a stub, too early to reload. */
async function backendIsServing(): Promise<boolean> {
  try {
    const response = await fetch(HEALTH_URL, { cache: 'no-store' })
    if (!response.ok) return false
    const payload = (await response.json()) as { status?: string }
    return payload.status === 'ok'
  } catch {
    return false
  }
}

async function waitUntil(reached: () => Promise<boolean>, budgetMs: number): Promise<boolean> {
  const deadline = Date.now() + budgetMs
  while (Date.now() < deadline) {
    if (await reached()) return true
    await sleep(POLL_INTERVAL_MS)
  }
  return false
}

function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => window.setTimeout(resolve, ms))
}
