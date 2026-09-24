import type { RouteRecordRaw } from 'vue-router'

// Свой префикс, а не `/tasks`: под `/tasks/…` живёт модуль задач, и меню, подсвечивающее пункт по
// префиксу пути, зажигало мониторинг на каждой его странице.
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
