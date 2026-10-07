import { defineStore } from 'pinia'
import { ref } from 'vue'

import { fetchAppFlags } from '@/api/app'

// The process-level switches from `.env` (`APP_*`), as the running backend sees them.
//
// Off until the backend answers: what a switch reveals (the development section) appearing a moment
// late costs nothing, while showing it to an installation where it is off would be wrong.
export const useAppStore = defineStore('app', () => {
  const devMode = ref(false)

  async function load(): Promise<void> {
    try {
      devMode.value = (await fetchAppFlags()).dev_mode
    } catch {
      devMode.value = false
    }
  }

  return { devMode, load }
})
