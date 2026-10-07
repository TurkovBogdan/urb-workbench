import { readonly, ref, watch, type Ref } from 'vue'

// The page transition runs on the CSS clock, not on frames: while the main thread is busy, the
// animation is not postponed but runs on idle. Measured on the research detail page — a 150 ms
// enter eaten by an 88 ms first render of the body: opacity went 0 → 0.05 → 0.99 in 22 ms, i.e.
// the page didn't fade in, it snapped. So heavy content waits for the transition to end — that
// turns the jerk into an extra loading line nobody minds.
//
// The flag is raised by the router guard: it fires before the new view mounts, while the
// transition's own `before-enter` hook fires later, and the view would already have decided there
// is no animation. It is cleared by the `<Transition>` in App.vue itself once the enter finishes.
const busy = ref(false)

export const routeTransitionBusy = readonly(busy)

export function beginRouteTransition(): void {
  busy.value = true
}

export function endRouteTransition(): void {
  busy.value = false
}

/**
 * Whether heavy content may render: `true` if no transition is running, otherwise as soon as it
 * ends.
 *
 * It never goes back to `false`: views live in `KeepAlive`, and on the next visit their content is
 * already rendered — hiding a finished picture for the duration of the animation would trade one
 * jerk for another.
 */
export function useAfterRouteTransition(): Readonly<Ref<boolean>> {
  const ready = ref(!busy.value)

  if (!ready.value) {
    const stop = watch(busy, (running) => {
      if (running) return
      ready.value = true
      stop()
    })
  }

  return readonly(ready)
}
