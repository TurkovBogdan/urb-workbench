import type { RouteRecordRaw } from 'vue-router'

// Its own prefix rather than `/tasks`: the tasks module lives under `/tasks/…`, and the menu, which
// highlights an item by path prefix, lit up monitoring on every one of its pages.
export const coreMonitoringRoutes: RouteRecordRaw[] = [
  {
    path: '/monitoring',
    name: 'monitoring',
    component: () => import('./views/TasksView.vue'),
    meta: { scroll: 'y', title: 'core_monitoring.page.title' },
  },
  {
    path: '/monitoring/:module/:code',
    name: 'monitoring-runs',
    component: () => import('./views/TaskRunsView.vue'),
    props: true,
    meta: { scroll: 'none', padding: false, title: 'core_monitoring.nav' },
  },
]
