import { inject, onActivated, onDeactivated, provide, readonly, ref, type InjectionKey, type Ref } from 'vue'

/**
 * Whether the page this component belongs to is the one on screen.
 *
 * Routed pages live in the global `KeepAlive`: leaving one does not unmount it, it only moves its
 * DOM into a detached container. Whatever the page put OUTSIDE its own DOM stays where it was —
 * the content of a `Teleport to="body"`, an open Vuetify overlay — and goes on reacting to the
 * window. Such a thing is shown only while this flag holds.
 *
 * The page frame (`PageLayout`) owns the flag and hands it down, rather than every component
 * keeping its own: a component mounted while its page is already away would start at `true`, and
 * a Tiptap node view — mounted by `render()`, outside the component tree — never gets the
 * KeepAlive hooks at all, while it does get the editor's `provide`.
 */
const PAGE_ACTIVE: InjectionKey<Readonly<Ref<boolean>>> = Symbol('page-active')

function ownFlag(): Readonly<Ref<boolean>> {
  const active = ref(true)
  onActivated(() => { active.value = true })
  onDeactivated(() => { active.value = false })
  return readonly(active)
}

/** The page frame's half: keep the flag and hand it to everything rendered inside the page. */
export function providePageActive(): Readonly<Ref<boolean>> {
  const active = ownFlag()
  provide(PAGE_ACTIVE, active)
  return active
}

/**
 * The page's flag. Outside a page frame — a component rendered on its own — the component's own
 * KeepAlive hooks stand in for it, and outside `KeepAlive` it stays `true`.
 */
export function usePageActive(): Readonly<Ref<boolean>> {
  return inject(PAGE_ACTIVE, null) ?? ownFlag()
}
