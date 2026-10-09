import { createApp } from 'vue'
import { createPinia } from 'pinia'
import App from './App.vue'
import router from './router'
import i18n from './plugins/i18n'
import vuetify from './plugins/vuetify'
import { useSettingsStore } from './stores/settings'
import { startSettingsSync } from './shared/utils/settings-sync'
import { setShellError } from './composables/useShellError'
import { useChangesStore } from './stores/changes'
import { useAppStore } from './stores/app'
import './styles/fonts.scss'
import './styles/main.scss'
import './styles/selection-controls.scss'
import './styles/layout.scss'
import './styles/typography.scss'
import './styles/transitions.scss'

const app = createApp(App)

// The last barrier before a blank screen: an unhandled exception inside a view becomes a
// "something broke" screen with a retry button rather than an empty #app. The error is still
// printed — the screen tells the person, the console tells the developer.
app.config.errorHandler = (err) => {
  console.error(err)
  setShellError('failure')
}

app.use(createPinia())
app.use(router)
app.use(i18n)
app.use(vuetify)

// Instantiating the settings store paints the chosen font families onto <html> before
// the first frame — leaving it to the first component that happens to use the store
// would swap the typeface after mount, in full view. It paints from the CACHE: the source of
// truth is the database, but fetching it before the first frame means showing the wrong styling
// or holding the splash.
useSettingsStore()

// Mount only after the initial navigation is fully resolved, so the destination
// route's `meta` (fullscreen/scroll) is already correct at first paint and the app
// chrome never flashes wrong. The static splash in index.html stays up until mount()
// replaces #app.
// Reconciling with the database happens after mount and off the critical render path: a backend
// booted by the MCP shim does not answer at once, and waiting for it here would freeze the splash.
void router.isReady().then(() => {
  app.mount('#app')
  void startSettingsSync()
  void useAppStore().load()
  // The data change feed also starts after mount: the connection is long-lived and paints
  // nothing in the first frame. Whatever arrives is shown quietly by the corner indicator (`ChangesIndicator`).
  useChangesStore().connect()
})
