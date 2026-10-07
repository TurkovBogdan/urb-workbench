import { onActivated, onBeforeUnmount, onDeactivated, onMounted, type ComponentPublicInstance, type Ref } from 'vue'

/**
 * Ctrl+F (Cmd+F) puts the cursor into the page's own search field instead of the browser's find
 * bar — for list pages, where "find" means finding an entry, not a word on screen: the find bar
 * sees only the rows already rendered, while the search field looks through the whole list.
 *
 * `scope` is the element or component holding the search: the first `SearchField` inside it takes
 * the focus, and the text already typed is selected so a new query replaces it.
 *
 * The key is matched by `code`, so the shortcut works in any keyboard layout. With a dialog open
 * it is left to the browser — the search field is behind the dialog. The listener lives only while
 * the page is on screen: routed pages stay alive in KeepAlive, and a hidden page must not catch
 * keys meant for the one in front. Both `onMounted` and `onActivated` attach it — the first covers
 * a page outside KeepAlive, and attaching the same listener twice is a no-op.
 */
export function useFindShortcut(scope: Ref<HTMLElement | ComponentPublicInstance | null>): void {
  function scopeElement(): Element | null {
    const target = scope.value
    if (!target) return null
    return target instanceof Element ? target : (target.$el as Element | null)
  }

  function focusSearch(event: KeyboardEvent) {
    if (!(event.ctrlKey || event.metaKey) || event.shiftKey || event.altKey || event.code !== 'KeyF') return
    if (document.querySelector('.v-dialog.v-overlay--active')) return
    const input = scopeElement()?.querySelector<HTMLInputElement>('.search-field input')
    if (!input) return
    event.preventDefault()
    input.focus()
    input.select()
  }

  function listen() {
    window.addEventListener('keydown', focusSearch)
  }

  function stop() {
    window.removeEventListener('keydown', focusSearch)
  }

  onMounted(listen)
  onActivated(listen)
  onDeactivated(stop)
  onBeforeUnmount(stop)
}
