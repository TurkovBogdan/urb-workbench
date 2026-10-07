import type { RouteRecordRaw } from 'vue-router'

// The tasks module section: the list, groups and the task detail page. Workspaces moved to their
// own module (`features/workspace/routes.ts`).
//
// A task lives as a PAGE at its own URL, not as a dialog over the list: it is where the work
// happens — editing text, moving the status, walking the subtask branch — and all of that needs
// room and its own entry in the navigation history.
export const tasksRoutes: RouteRecordRaw[] = [
  // The section root is the list. `/tasks` used to host the scheduler monitoring (now
  // `/monitoring`), and an old link must not hit "page not found".
  { path: '/tasks', redirect: '/tasks/list' },
  {
    path: '/tasks/list',
    name: 'tasks-list',
    component: () => import('./views/TasksView.vue'),
    meta: { scroll: 'y', title: 'tasks.nav_tasks' },
  },
  {
    path: '/tasks/groups',
    name: 'tasks-groups',
    component: () => import('./views/GroupsView.vue'),
    meta: { scroll: 'y', title: 'tasks.nav_groups' },
  },
  {
    path: '/tasks/task/:code',
    name: 'tasks-task',
    component: () => import('./views/TaskView.vue'),
    meta: { scroll: 'y', title: 'tasks.task.detail.title' },
  },
]
