import { IconAlertTriangle, IconError404, IconLock, IconWifiOff, type Icon } from '@tabler/icons-vue'

// Catalogue of failures where there is nothing to see on the page and a screen is shown instead of
// the content. An OPERATION failure (a button didn't work) never belongs here — its answer goes
// next to the action, the screen must not be taken away. "Entity not found" is not a screen either,
// but a state inside the section.

export type ErrorKind = 'not-found' | 'forbidden' | 'failure' | 'offline'

/** Ways out of the screen. The last in the list is rendered as the primary action. */
export type ErrorAction = 'back' | 'home' | 'retry'

export interface ErrorKindSpec {
  icon: Icon
  /** Response code; a failure with no response (no connection) has none. */
  code: string | null
  /** Dictionary branch `common.errors.<key>` with the title and description. */
  key: string
  actions: ErrorAction[]
}

export const ERROR_KINDS: Record<ErrorKind, ErrorKindSpec> = {
  'not-found': { icon: IconError404, code: null, key: 'notFound', actions: ['back', 'home'] },
  forbidden: { icon: IconLock, code: '403', key: 'forbidden', actions: ['back', 'home'] },
  failure: { icon: IconAlertTriangle, code: '500', key: 'failure', actions: ['home', 'retry'] },
  offline: { icon: IconWifiOff, code: null, key: 'offline', actions: ['retry'] },
}
