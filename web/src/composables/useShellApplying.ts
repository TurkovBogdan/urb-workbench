import { computed, readonly, ref } from 'vue'

// While the server restarts with new settings the shell has nothing usable to offer: every request
// fails until it is back. So the whole layout gives way to one full-screen banner instead of a
// spinner inside a page that still looks clickable.
//
// The page underneath stays mounted on purpose: if the server never returns, the banner lifts and
// that page reports the failure with the form exactly as the person left it.
interface Applying {
  /** Where the server comes back when it moves to another host/port; `null` — right here. */
  movingTo: string | null
}

const state = ref<Applying | null>(null)

export const shellApplying = readonly(state)
export const isShellApplying = computed(() => state.value !== null)

export function beginShellApplying(): void {
  state.value = { movingTo: null }
}

export function announceShellMove(origin: string): void {
  if (state.value) state.value.movingTo = origin
}

export function endShellApplying(): void {
  state.value = null
}
