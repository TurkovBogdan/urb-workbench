// The codex section's addresses, in one place. Two entries in the sidebar — the materials (the
// canvas editor) and the available codexes (every codex and its mount) — so their prefixes must
// not nest: the sidebar lights an entry by prefix, and `/codex` under `/codex/…` would light both.
// `workbench/entities/codex.py::CodexPage` builds the same materials address for `interface_open`.
export const CODEX_MATERIALS = '/codex/materials'
export const CODEX_AVAILABLE = '/codex/available'

/** The materials editor opened on a codex or a note — one address for both, they share CODEX@. */
export function codexNodePath(code: string): string {
  return `${CODEX_MATERIALS}/${encodeURIComponent(code)}`
}

/**
 * A record's virtual path as the person reads it: from the canvas root, with a leading slash —
 * `/python/test/factories`. The API keeps the path bare (`python/test`), as the agent passes it;
 * the slash is added only on screen, in every place a path is shown.
 */
export function displayPath(path: string): string {
  return path ? `/${path.replace(/^\/+/, '')}` : ''
}
