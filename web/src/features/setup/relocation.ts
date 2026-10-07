import type { ServerMove } from './api'

// After a host/port change the server comes back at another origin: the page has to wait for THAT
// one and go there, otherwise it polls an address nobody will ever answer again.

const WILDCARD_HOSTS = new Set(['', '0.0.0.0', '::'])
const LOOPBACK_HOSTS = new Set(['localhost', '127.0.0.1', '::1', '[::1]'])

/** The origin to follow after the restart; `null` — the page stays where it is. */
export function relocatedOrigin(move: ServerMove | null): string | null {
  if (!move) return null
  const url = new URL(window.location.origin)
  // Served not by the backend itself (Vite in dev, a reverse proxy): where that front goes after
  // the move is unknown here, so the page does not guess.
  if (pagePort(url) !== String(move.from_port)) return null

  url.port = String(move.port)
  if (hostnameChanges(move, url.hostname)) url.hostname = urlHost(move.host)
  return url.origin === window.location.origin ? null : url.origin
}

/** A cross-origin probe: `no-cors` resolves on any HTTP answer and rejects while nobody listens. */
export async function isOriginUp(origin: string): Promise<boolean> {
  try {
    await fetch(`${origin}/internal/health`, { mode: 'no-cors', cache: 'no-store' })
    return true
  } catch {
    return false
  }
}

function pagePort(url: URL): string {
  return url.port || (url.protocol === 'https:' ? '443' : '80')
}

// The name the person typed keeps working whenever the new bind still covers it: a wildcard
// listens on every interface, an unchanged host is the same machine, and loopback is loopback
// whichever spelling is used.
function hostnameChanges(move: ServerMove, current: string): boolean {
  if (WILDCARD_HOSTS.has(move.host)) return false
  if (move.host === move.from_host) return false
  if (LOOPBACK_HOSTS.has(move.host) && LOOPBACK_HOSTS.has(current)) return false
  return true
}

function urlHost(host: string): string {
  return host.includes(':') && !host.startsWith('[') ? `[${host}]` : host
}
