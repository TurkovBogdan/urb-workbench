import type { RouteRecordRaw } from 'vue-router'

// Страница модулей (`views/SettingsView.vue`) маршрута не получает: настраиваемых параметров не
// объявляет ни один модуль сборки, и раздел показывал пустой экран с кнопками сохранения. Код
// страницы оставлен — вернуть её значит вернуть сюда запись и строку в меню.
export const settingsRoutes: RouteRecordRaw[] = [
  {
    path: '/settings/interface',
    name: 'settings-interface',
    component: () => import('./views/InterfaceView.vue'),
    meta: { scroll: 'y', title: 'settings.interface.page.title' },
  },
]
