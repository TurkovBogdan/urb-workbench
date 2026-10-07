import type { RouteRecordRaw } from 'vue-router'

// The workspaces section. A single page — their list; choosing the current one lives not here but
// in the sidebar (`WorkspaceSwitcher`), because it is the context of the whole app, not a place in
// it.
//
// The address is top-level (`/workspaces`), not inside tasks: the workspace stopped belonging to
// the tasks module and became a shared level for everyone. The old address is kept as a redirect —
// links from empty states and other people's bookmarks point at it.
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
