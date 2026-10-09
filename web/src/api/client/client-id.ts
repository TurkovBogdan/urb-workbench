// Id of this tab for the change feed (`core_changes`).
//
// Every request to our own backend carries it in `X-Client-Id`; the backend puts it into the feed
// message as `origin`, so the tab recognises the echo of its own saves (`stores/changes.ts`). It
// lives until the page reloads and is never stored: two tabs are two sources — otherwise an edit
// made in one would count as "own" in the other, and the other would never see it.
export const CLIENT_ID_HEADER = 'X-Client-Id'

// `randomUUID` exists only in a secure context (https, localhost); a tab opened over plain http at
// a network address would throw on startup. The fallback is unique enough for the lifetime of a
// tab.
export const CLIENT_ID: string =
  typeof crypto.randomUUID === 'function'
    ? crypto.randomUUID()
    : `${Date.now().toString(36)}-${Math.random().toString(36).slice(2)}`
