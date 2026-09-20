import type { RouteRecordRaw } from 'vue-router'

// Раздел пространств. Страница одна — их список; выбор текущего живёт не здесь, а в боковой
// панели (`WorkspaceSwitcher`), потому что это контекст всего приложения, а не место в нём.
//
// Адрес корневой (`/workspaces`), а не внутри задач: пространство перестало принадлежать модулю
// задач и стало общим уровнем для всех. Старый адрес оставлен редиректом — на него смотрят
// ссылки из пустых состояний и из чужих закладок.
export const workspacesRoutes: RouteRecordRaw[] = [
  {
    path: '/workspaces',
    name: 'workspaces',
    component: () => import('./views/WorkspacesView.vue'),
    meta: { scroll: 'y', title: 'workspace.nav' },
  },
  {
    path: '/tasks/workspaces',
    name: 'tasks-workspaces-legacy',
    redirect: { path: '/workspaces' },
  },
]
