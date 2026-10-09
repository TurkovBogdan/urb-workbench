// A ref that survives a page reload: the value lives in localStorage, the state is a plain typed
// ref, and a codec translates between them.
//
// A value equal to the default is NOT written (the key is removed): storage keeps only deliberate
// deviations, and a change of the default in code reaches everyone who didn't touch it.
//
// Lives apart from `stores/settings` because such a ref has two homes: the person's settings and
// interface state (`stores/ui-state`). A shared helper in one of them would mean the other imports
// a foreign store for one line of code.
//
// Interface settings take `synced` from here (the neighbouring file): there storage becomes a
// cache on top of the database. What stays here is what lives only in the browser.
import { ref, watch, type Ref } from 'vue'

export interface Codec<T> {
  parse: (raw: string) => T
  serialize: (value: T) => string
}

export const boolCodec: Codec<boolean> = {
  parse: (raw) => raw === '1',
  serialize: (v) => (v ? '1' : '0'),
}

export const strCodec: Codec<string> = { parse: (raw) => raw, serialize: (v) => v }

export const intCodec: Codec<number> = {
  parse: (raw) => Number.parseInt(raw, 10),
  serialize: (v) => String(v),
}

export function persisted<T>(key: string, def: T, codec: Codec<T>): Ref<T> {
  const has = typeof localStorage !== 'undefined'
  const raw = has ? localStorage.getItem(key) : null
  const state = ref(raw === null ? def : codec.parse(raw)) as Ref<T>
  watch(state, (v) => {
    if (!has) return
    if (v === def) localStorage.removeItem(key)
    else localStorage.setItem(key, codec.serialize(v))
  })
  return state
}
