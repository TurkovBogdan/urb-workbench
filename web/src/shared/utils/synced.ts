// An interface setting ref: the same as `persisted`, plus sending to the database.
//
// `persisted` manages the cache (a value equal to the default is removed from it), and two things
// are added here: registering the key with the sync mechanism and queueing the change for sending.
//
// The watcher is synchronous on purpose: the "applying from outside" flag is cleared right after
// the assignment, and a deferred watcher would see the flag already cleared — a value just read
// from the database would be sent straight back to it.
import { watch, type Ref } from 'vue'

import type { SettingValue } from '@/api/interface-settings'
import { persisted, type Codec } from './persisted'
import { enqueue, isApplyingExternal, registerSetting } from './settings-sync'

export function synced<T extends SettingValue>(key: string, def: T, codec: Codec<T>): Ref<T> {
  const state = persisted(key, def, codec)
  registerSetting(key, state, def, codec)
  watch(
    state,
    () => {
      if (!isApplyingExternal()) enqueue(key)
    },
    { flush: 'sync' },
  )
  return state
}
