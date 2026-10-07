import { computed, ref, type Ref } from 'vue'

/** Where a dragged row landed: exactly one neighbour names the place, never a `sort` number. */
export type ReorderPlace = { after_code: string } | { before_code: string }

export interface ListReorderOptions<T extends { code: string }> {
  /** The list the store renders; the row is moved in it at once, before the backend answers. */
  items: Ref<T[]>
  request: (code: string, place: ReorderPlace) => Promise<unknown>
  /** The re-read that reconciles the screen with the database once the chain has drained. */
  reload: () => Promise<unknown>
  /** Called with the new order right after the optimistic move. */
  onMoved?: (items: T[]) => void
}

/**
 * Reordering a flat list by dragging: on screen at once, then in the database.
 *
 * The drag library reverts its own DOM reorder before `onEnd` and lets Vue redraw from the array,
 * so without moving the row here first it would sit in its old place until the re-read. The re-read
 * still follows — once, when the chain has drained — as reconciliation: if the backend agrees,
 * nothing moves; if it refused (the toast says why) or the list was stale, the backend wins.
 *
 * Requests go as a CHAIN, in gesture order: two quick drops must not race each other to the backend
 * and land in reverse.
 */
export function useListReorder<T extends { code: string }>(options: ListReorderOptions<T>) {
  const { items, request, reload, onMoved } = options

  let chain: Promise<void> = Promise.resolve()
  const inFlight = ref(0)

  /** Moves are on their way: a re-read now would show an order the backend has not reached yet. */
  const moving = computed(() => inFlight.value > 0)

  function move(code: string, toIndex: number) {
    const from = items.value.findIndex((item) => item.code === code)
    if (from < 0 || from === toIndex) return
    const next = [...items.value]
    const [row] = next.splice(from, 1)
    next.splice(toIndex, 0, row)
    items.value = next
    onMoved?.(next)

    // The neighbour above names the place; at the very top there is none, so the one below does.
    const place: ReorderPlace = toIndex > 0
      ? { after_code: next[toIndex - 1].code }
      : { before_code: next[1].code }

    inFlight.value += 1
    chain = chain
      .then(() => request(code, place))
      .then(() => undefined, () => undefined)
      .finally(() => {
        inFlight.value -= 1
        if (inFlight.value === 0) void reload()
      })
  }

  return { move, moving }
}
