import { onBeforeUnmount, onMounted, watch, type Ref } from 'vue'
import { usePageActive } from '@/composables/usePageActive'
import { routeTransitionBusy } from '@/composables/useRouteTransition'

/**
 * The life of an editor toolbar teleported to <body> and placed from the editor's coordinates.
 *
 * Teleported, the toolbar does not leave with its page (KeepAlive), so it follows the page's flag:
 * the page goes away — the toolbar hides and stops listening to the window, or every scroll of the
 * page in front would re-place it from an editor detached from the document, whose coordinates are
 * all zeros (the top left corner). The page comes back — the toolbar is placed again for the
 * selection the editor kept, once the enter animation is over: during it the page is shifted by
 * its transform, and the toolbar would stand off its text.
 *
 * `place` decides whether to show and where; `hide` closes unconditionally.
 */
export function usePanelPlacement(place: () => void, hide: () => void): Readonly<Ref<boolean>> {
  const pageActive = usePageActive()

  function listen(): void {
    window.addEventListener('scroll', place, true)
    window.addEventListener('resize', place)
  }

  function stop(): void {
    window.removeEventListener('scroll', place, true)
    window.removeEventListener('resize', place)
  }

  watch(pageActive, (active) => {
    if (!active) {
      stop()
      hide()
      return
    }
    listen()
    if (!routeTransitionBusy.value) place()
  })

  watch(routeTransitionBusy, (busy) => {
    if (!busy && pageActive.value) place()
  })

  onMounted(() => {
    if (pageActive.value) listen()
  })
  onBeforeUnmount(stop)

  return pageActive
}
