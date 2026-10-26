// Where files dragged in from the computer may go, for the whole window.
//
// Left to itself, a browser that gets a file dropped anywhere but on a drop zone leaves the page to
// open the file, and a plain text field takes the file's path as typed text. So one guard watches
// the window: while files are over it, every `dragenter` / `dragover` is cancelled — the page, not
// the browser, decides — and the drop effect says what will happen: `copy` over a zone that takes
// files, `none` anywhere else, which the system shows as the "no" cursor and which turns a drop
// there into a cancelled drag. The guard is the only one setting the effect; a zone only registers
// and handles the drop it accepted.
//
// It also knows, for the zones to show it, whether files are over the window at all (every zone
// that would take them marks itself) and which zone is under the pointer (that one fills).
//
// A drag from the computer has no `dragend` here, so its end is read from the events that do come:
// the drop; a `dragleave` whose `relatedTarget` is null — the pointer left the window, or Escape
// cancelled the drag (both end in a `dragleave` on the element under the pointer). Safari reports a
// null `relatedTarget` on every boundary, not only the window's, so the reset waits `leaveMs` for
// the next `dragenter` / `dragover` to cancel it. A watchdog resets after `idleMs` without a
// `dragover`, which the browser repeats while the pointer is over the page, even standing still.
//
// A drag that started on this page — a block by its handle, a piece of selected text, a picture —
// is not the guard's business, even when the browser lists `Files` among its types (a dragged
// picture): `dragstart` fires only for drags begun in this document, and `dragend` closes them. A
// source removed mid-drag (a block that moved) sends its `dragend` nowhere, so a drop and the first
// `pointermove` after the drag close it too — no pointer events come while any drag is running.
//
// Framework-free: the state goes out through `onState`, checked under Node
// (`tests/apps/web_file_drop.mjs`).
import { carriesFiles } from './fileDrop'

/** A place that may take files: asked at the moment of every `dragover`. */
export interface FileZone {
  accepts(): boolean
}

export interface FileDragState {
  /** Files from the computer are over the window. */
  active: boolean
  /** The zone under the pointer, accepting or not; `null` — none. */
  zone: FileZone | null
}

/** The part of a drag event (or of a `pointermove`) the guard reads and writes. */
export interface DragEventLike {
  type: string
  target: unknown
  relatedTarget?: unknown
  dataTransfer?: { types: ArrayLike<string>; dropEffect: string } | null
  preventDefault(): void
}

export interface FileDragOptions {
  /** The zone the event's target lies in — its own or its nearest registered ancestor's. */
  zoneOf: (target: unknown) => FileZone | null
  onState: (state: FileDragState) => void
  /** The timer — replaceable where time is not real. Returns the cancel. */
  later?: (run: () => void, ms: number) => () => void
  leaveMs?: number
  idleMs?: number
}

export interface FileDragTracker {
  handle(event: DragEventLike): void
  state(): FileDragState
}

const LEAVE_MS = 50
const IDLE_MS = 1500

const realTimer = (run: () => void, ms: number): (() => void) => {
  const id = setTimeout(run, ms)
  return () => clearTimeout(id)
}

export function createFileDragTracker(options: FileDragOptions): FileDragTracker {
  const later = options.later ?? realTimer
  const leaveMs = options.leaveMs ?? LEAVE_MS
  const idleMs = options.idleMs ?? IDLE_MS

  let current: FileDragState = { active: false, zone: null }
  let internal = false
  let cancelLeave: (() => void) | null = null
  let cancelIdle: (() => void) | null = null

  function publish(next: FileDragState): void {
    if (next.active === current.active && next.zone === current.zone) return
    current = next
    options.onState(current)
  }

  function stopTimers(): void {
    cancelLeave?.()
    cancelLeave = null
    cancelIdle?.()
    cancelIdle = null
  }

  function reset(): void {
    stopTimers()
    publish({ active: false, zone: null })
  }

  function over(event: DragEventLike): void {
    event.preventDefault()
    const zone = options.zoneOf(event.target)
    const accepted = zone?.accepts() ?? false
    if (event.dataTransfer) event.dataTransfer.dropEffect = accepted ? 'copy' : 'none'
    cancelLeave?.()
    cancelLeave = null
    cancelIdle?.()
    cancelIdle = later(reset, idleMs)
    publish({ active: true, zone })
  }

  function handle(event: DragEventLike): void {
    if (event.type === 'dragstart') {
      internal = true
      reset()
      return
    }
    if (event.type === 'dragend' || event.type === 'pointermove') {
      internal = false
      if (current.active) reset()
      return
    }
    if (internal) {
      if (event.type === 'drop') internal = false
      return
    }
    if (!carriesFiles(event.dataTransfer?.types)) return
    switch (event.type) {
      case 'dragenter':
      case 'dragover':
        over(event)
        return
      case 'dragleave':
        if (event.relatedTarget) return
        cancelLeave?.()
        cancelLeave = later(reset, leaveMs)
        return
      case 'drop':
        // Taken by a zone or not, the browser must not open the file.
        event.preventDefault()
        reset()
    }
  }

  return { handle, state: () => current }
}
