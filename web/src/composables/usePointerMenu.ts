import { computed, onBeforeUnmount, ref, watch } from 'vue'

/**
 * An action menu that opens two ways — from its "⋯" button and on a right click at the pointer —
 * and behaves the same on every surface that has one (a task row, a group card).
 *
 * `isInside` says which presses belong to the menu: its own content and the button that toggles
 * it. Any other press, of any mouse button, closes the menu. Vuetify closes a menu only on a left
 * click outside it, so a right or middle press would leave it open, and right-clicking down a list
 * would stack up one menu per row. The toggling button counts as inside: closing on its press
 * would only let the click reopen the menu.
 *
 * Bind `placement` onto the `VMenu`: at the pointer the menu opens from its corner and closes on
 * scroll — it is pinned to a screen point, not to the row, and scrolling would leave it hanging
 * over someone else's entry. From the button it hangs off the button as usual.
 */
export function usePointerMenu(isInside: (target: Node) => boolean) {
  const open = ref(false)
  /** Where a right click opened the menu; `null` — it hangs off the "⋯" button. */
  const point = ref<[x: number, y: number] | null>(null)

  /** Shift keeps the browser's own menu reachable: open in a new tab, copy the link, inspect. */
  function openAt(event: MouseEvent): boolean {
    if (event.shiftKey) return false
    event.preventDefault()
    point.value = [event.clientX, event.clientY]
    open.value = true
    return true
  }

  /** Call from the "⋯" button's click: the menu goes back to hanging off it. */
  function fromButton() {
    point.value = null
  }

  function closeOnPressOutside(event: PointerEvent) {
    if (isInside(event.target as Node)) return
    open.value = false
  }

  function stopWatchingPresses() {
    document.removeEventListener('pointerdown', closeOnPressOutside, true)
  }

  watch(open, (isOpen) => {
    if (isOpen) document.addEventListener('pointerdown', closeOnPressOutside, true)
    else stopWatchingPresses()
  })

  onBeforeUnmount(stopWatchingPresses)

  const placement = computed(() => ({
    target: point.value ?? undefined,
    location: point.value ? 'bottom start' as const : 'bottom end' as const,
    offset: point.value ? 0 : 4,
    scrollStrategy: point.value ? 'close' as const : 'reposition' as const,
  }))

  return { open, point, openAt, fromButton, placement }
}
