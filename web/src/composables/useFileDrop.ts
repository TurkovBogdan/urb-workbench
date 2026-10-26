// Files from the computer over the window, for Vue: the guard (`shared/utils/fileDrag.ts`) installed
// once for the app, and the zones that register with it.
//
// A zone is an element and a question — "would you take files right now?". It gets three answers
// back, each for its own look:
//
// - `armed` — files are over the window and this zone would take them: a quiet mark, so the person
//   sees where files can go before aiming;
// - `over` — and the pointer is on it: the zone fills, the one place the drop will land;
// - `refused` — the pointer is on it and it would not take them: whatever it would draw for a drop
//   stays hidden, the cursor already says "no".
//
// The zone handles the drop it accepted itself; the guard has set the drop effect and stops the
// browser from opening a file dropped anywhere else.
//
// The guard listens on the window in the bubbling phase, after every element on the way: a text
// editor skips its own `drop` handling when the event comes to it cancelled already.
import { computed, onBeforeUnmount, shallowReactive, watch, type ComponentPublicInstance, type ComputedRef, type Ref } from 'vue'

import { createFileDragTracker, type DragEventLike, type FileZone } from '@/shared/utils/fileDrag'

const state = shallowReactive<{ active: boolean; zone: FileZone | null }>({ active: false, zone: null })
const zones = new WeakMap<Element, FileZone>()

function zoneOf(target: unknown): FileZone | null {
  let node: Node | null = target instanceof Node ? target : null
  while (node) {
    if (node instanceof Element) {
      const zone = zones.get(node)
      if (zone) return zone
    }
    node = node.parentNode
  }
  return null
}

const EVENTS = ['dragstart', 'dragend', 'dragenter', 'dragover', 'dragleave', 'drop', 'pointermove'] as const

let uninstall: (() => void) | null = null

/** Watch the window for files from the computer. Once for the app; a second call changes nothing. */
export function installFileDragGuard(target: Window = window): () => void {
  if (uninstall) return uninstall
  const tracker = createFileDragTracker({
    zoneOf,
    onState: (next) => {
      state.active = next.active
      state.zone = next.zone
    },
  })
  const listener = (event: Event) => tracker.handle(event as unknown as DragEventLike)
  for (const name of EVENTS) target.addEventListener(name, listener, { passive: name === 'pointermove' })
  uninstall = () => {
    for (const name of EVENTS) target.removeEventListener(name, listener)
    uninstall = null
  }
  return uninstall
}

/** Files from the computer are over the window. */
export const filesOverWindow: ComputedRef<boolean> = computed(() => state.active)

export interface FileDropZone {
  armed: ComputedRef<boolean>
  over: ComputedRef<boolean>
  refused: ComputedRef<boolean>
}

type ZoneElement = HTMLElement | ComponentPublicInstance | null | undefined

function elementOf(target: ZoneElement): Element | null {
  if (!target) return null
  if (target instanceof Element) return target
  const el = (target as ComponentPublicInstance).$el
  return el instanceof Element ? el : null
}

/** Register `element` as a place that takes files whenever `accepts()` says so. */
export function useFileDropZone(element: Ref<ZoneElement>, accepts: () => boolean): FileDropZone {
  const zone: FileZone = { accepts }
  let bound: Element | null = null

  watch(element, (target) => {
    if (bound) zones.delete(bound)
    bound = elementOf(target)
    if (bound) zones.set(bound, zone)
  }, { immediate: true, flush: 'post' })

  onBeforeUnmount(() => {
    if (bound) zones.delete(bound)
    bound = null
    if (state.zone === zone) state.zone = null
  })

  return {
    armed: computed(() => state.active && accepts()),
    over: computed(() => state.zone === zone && accepts()),
    refused: computed(() => state.zone === zone && !accepts()),
  }
}
