// The files card's upload queue: files sent one request each, one at a time, in the order given.
//
// The card outlives its holder — a page that shows another task keeps its components — so a file
// takes its holder and that holder's upload with it at the moment it is queued. When its turn comes
// it goes there, whatever the card shows by then: the person dropped it on that holder, and sending
// it elsewhere would be the one wrong outcome. Its row stays that holder's too, and the card shows
// the rows of the holder on screen only.
//
// Framework-free: the rows live in a `state` object the card makes reactive, so the queue is
// checked under Node (`tests/apps/web_upload_queue.mjs`).

/**
 * How one upload ended, worded by the holder. A refusal that leaves the holder as the person
 * wanted it (the file is there already) is `calm`: a notice, not an error. `code` — the file the
 * holder now has (sent, or the one it held already), for the card to point at.
 */
export type UploadOutcome = { ok: true; code?: string } | { ok: false; text: string; calm?: boolean; code?: string }

/** Send one file into the holder; `progress` takes the share sent, 0…1. */
export type UploadFile = (file: File, progress: (share: number) => void) => Promise<UploadOutcome>

export interface UploadRow {
  id: number
  /** The holder the file was dropped on — the card's `holder` key at that moment. */
  holder: string
  name: string
  mime: string
  state: 'queued' | 'sending' | 'failed' | 'notice'
  share: number
  text: string
}

export interface UploadQueueOptions {
  /** How long a calm outcome stays before it goes by itself. */
  noticeMs: number
  /** The timer — replaceable where time is not real. */
  later?: (run: () => void, ms: number) => void
  /** A sent file's outcome, as the holder gave it — once its row is settled. */
  onOutcome?: (holder: string, outcome: UploadOutcome) => void
}

export interface UploadQueue {
  enqueue(holder: string, send: UploadFile, files: Iterable<File>): void
  /** A file refused before it is sent (a folder, over the ceiling): a failed row at once, no request. */
  refuse(holder: string, name: string, mime: string, text: string): void
  dismiss(id: number): void
  rowsOf(holder: string): UploadRow[]
}

export function createUploadQueue(state: { rows: UploadRow[] }, options: UploadQueueOptions): UploadQueue {
  const later = options.later ?? ((run, ms) => { setTimeout(run, ms) })
  // The files and their uploads stay out of the rows: nothing reactive has business proxying them.
  const waiting = new Map<number, { holder: string; file: File; send: UploadFile }>()
  let nextId = 0
  let pumping = false

  function patch(id: number, change: Partial<UploadRow>): void {
    state.rows = state.rows.map((row) => (row.id === id ? { ...row, ...change } : row))
  }

  function dismiss(id: number): void {
    state.rows = state.rows.filter((row) => row.id !== id)
  }

  async function pump(): Promise<void> {
    if (pumping) return
    pumping = true
    try {
      for (let next = state.rows.find((row) => row.state === 'queued'); next; next = state.rows.find((row) => row.state === 'queued')) {
        const id = next.id
        const entry = waiting.get(id)
        waiting.delete(id)
        if (!entry) {
          dismiss(id)
          continue
        }
        patch(id, { state: 'sending' })
        const outcome = await entry.send(entry.file, (share) => patch(id, { share }))
        if (outcome.ok) {
          dismiss(id)
        } else if (outcome.calm) {
          patch(id, { state: 'notice', text: outcome.text })
          later(() => dismiss(id), options.noticeMs)
        } else {
          patch(id, { state: 'failed', text: outcome.text })
        }
        options.onOutcome?.(entry.holder, outcome)
      }
    } finally {
      pumping = false
    }
  }

  return {
    enqueue(holder, send, files) {
      const added: UploadRow[] = []
      for (const file of files) {
        const id = nextId++
        waiting.set(id, { holder, file, send })
        added.push({ id, holder, name: file.name, mime: file.type, state: 'queued', share: 0, text: '' })
      }
      state.rows = [...state.rows, ...added]
      void pump()
    },
    refuse(holder, name, mime, text) {
      state.rows = [...state.rows, { id: nextId++, holder, name, mime, state: 'failed', share: 0, text }]
    },
    dismiss,
    rowsOf: (holder) => state.rows.filter((row) => row.holder === holder),
  }
}
