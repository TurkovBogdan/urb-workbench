import type { RouteRecordRaw } from 'vue-router'

// The modules page (`views/SettingsView.vue`) gets no route: no module in this build declares
// configurable parameters, and the section showed an empty screen with save buttons. The page code
// is kept — bringing it back means restoring the record here and the line in the menu.
export const settingsRoutes: RouteRecordRaw[] = [
  {
    path: '/settings/interface',
    name: 'settings-interface',
    component: () => import('./views/InterfaceView.vue'),
    meta: { scroll: 'y', title: 'settings.interface.page.title' },
  },
]
