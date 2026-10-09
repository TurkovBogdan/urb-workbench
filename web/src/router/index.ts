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
  // Not scrolling but recognising it: the handler scrolls nothing (returns `false`) and only
  // records whether this is a history return or a new transition — `PageLayout` scrolls the
  // content zone.
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
    // Doesn't have to precede the scheduler (`/tasks`): the module's pages live at two segments,
    // and it has one. They share exactly one three-segment route — the old task link versus
    // `/tasks/:module/:code` — and the conflict is settled not by declaration order but by
    // vue-router's ranking: a static segment outweighs a param (see features/tasks/routes.ts).
    ...tasksRoutes,
    ...workspacesRoutes,
    ...settingsRoutes,
    ...setupRoutes,
    ...aboutRoutes,
    // Research and web search (`features/research`, `features/web_search`) are the donor's domain:
    // the feature code is kept, but their routes are not registered, and there is no backend
    // behind them anymore. Integrations are gone entirely — with the `core_connectors` module and
    // their feature.
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
