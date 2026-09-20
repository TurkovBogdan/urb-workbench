import { createRouter, createWebHistory } from 'vue-router'

import { setupGuards } from './guards'
import { trackNavigationKind } from './scroll'
import { setupRoutePrefetch } from './prefetch'
import { setupChunkReload } from './reload'
import { designSystemRoutes } from './design-system'
import { aboutRoutes } from '../features/about/routes'
import { coreMcpRoutes } from '../features/core_mcp/routes'
import { coreMonitoringRoutes } from '../features/core_monitoring/routes'
import { settingsRoutes } from '../features/settings/routes'
import { setupRoutes } from '../features/setup/routes'
import { tasksRoutes } from '../features/tasks/routes'
import { workspacesRoutes } from '../features/workspace/routes'

const router = createRouter({
  history: createWebHistory(import.meta.env.BASE_URL),
  // Не прокрутка, а её опознание: обработчик ничего не мотает (возвращает `false`) и только
  // запоминает, возврат это по истории или новый переход — мотает зону содержимого `PageLayout`.
  scrollBehavior: trackNavigationKind,
  routes: [
    { path: '/', redirect: '/home' },
    {
      path: '/home',
      name: 'home',
      component: () => import('../views/HomeView.vue'),
      meta: { scroll: 'y' },
    },
    ...designSystemRoutes,
    ...coreMcpRoutes,
    ...coreMonitoringRoutes,
    // Раньше планировщика (`/tasks`) не обязано быть: страницы модуля живут двумя сегментами, а
    // у него один. Трёхсегментный маршрут у них общий ровно один — старая ссылка на задачу
    // против `/tasks/:module/:code`, — и спор решает не порядок записи, а ранжирование
    // vue-router: статический сегмент весомее параметра (см. features/tasks/routes.ts).
    ...tasksRoutes,
    ...workspacesRoutes,
    ...settingsRoutes,
    ...setupRoutes,
    ...aboutRoutes,
    // Исследования и веб-поиск (`features/research`, `features/web_search`) — домен донора:
    // код фич оставлен, но их маршруты не регистрируются, и бекенда под ними больше нет.
    // Интеграции уехали целиком — вместе с модулем `core_connectors` и своей фичей.
    // Catch-all 404 — kept LAST so it can't shadow any route declared above it.
    // Renders the 404 inside the app shell.
    {
      path: '/:pathMatch(.*)*',
      name: 'not-found',
      component: () => import('../views/errors/NotFoundView.vue'),
      meta: { scroll: 'none', padding: false, title: 'common.errors.notFound.title' },
    },
  ],
})

setupGuards(router)
setupRoutePrefetch(router)
setupChunkReload(router)

export default router
