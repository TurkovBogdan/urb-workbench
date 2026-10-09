import { readonly, ref } from 'vue'

// Toasts. Built around one rule: a failure the screen did not show itself must pop up here.
// Silence must take an explicit action, not happen by itself.
//
// A module, not Pinia: the API client writes here, i.e. code outside components.

/** Level = palette tone. Names match the token dictionary, including `warn`. */
export type ToastLevel = 'success' | 'info' | 'warn' | 'error'

/**
 * One button that undoes or follows up on the news — "Restore" after a delete. Pressing it closes
 * the toast first: the action is the person's answer to the message, and the message must not
 * hang on screen while its own answer is being carried out.
 */
export interface ToastAction {
  label: string
  run: () => unknown
}

export interface Toast {
  id: number
  text: string
  level: ToastLevel
  /** After how many milliseconds to dismiss; 0 — keep until the person closes it. */
  timeout: number
  action?: ToastAction
}

/** How long a toast lives. One duration for all levels: the ring at the close button counts it. */
const DEFAULT_TIMEOUT = 5000

/**
 * Queue cap. Toasts are shown one at a time, and without a cap the tenth failure would get its turn
 * forty-five seconds later — when nobody needs it anymore. We evict THE OLDEST: a fresh failure is
 * closer to what the person is doing now.
 */
const MAX_QUEUED = 3

const items = ref<Toast[]>([])
let lastId = 0

export const toasts = readonly(items)

/**
 * Show a toast. A repeat of the same "text + level" pair is ignored while the previous one is up:
 * five parallel requests that failed the same way are one piece of news, not five. The level is
 * part of the key on purpose: the same text as a success and as an error is different news.
 */
export function pushToast(
  text: string,
  level: ToastLevel = 'error',
  timeout = DEFAULT_TIMEOUT,
  action?: ToastAction,
): void {
  const message = text.trim()
  if (message === '') {
    return
  }

  for (const toast of items.value) {
    if (toast.text === message && toast.level === level) {
      return
    }
  }

  lastId += 1

  const next = [...items.value, { id: lastId, text: message, level, timeout, action }]
  items.value = next.length > MAX_QUEUED ? next.slice(next.length - MAX_QUEUED) : next
}

export function dismissToast(id: number): void {
  items.value = items.value.filter(toast => toast.id !== id)
}

export function clearToasts(): void {
  items.value = []
}
