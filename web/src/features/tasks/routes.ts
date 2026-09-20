import type { RouteRecordRaw } from 'vue-router'

// Раздел модуля задач: список, группы и деталка задачи. Пространства уехали в свой модуль
// (`features/workspace/routes.ts`).
//
// Задача живёт СТРАНИЦЕЙ по собственному адресу, а не окном поверх списка: в ней работают —
// правят текст, водят статус, ходят по ветке подзадач, — и всё это требует места и своей записи
// в истории переходов.
//
// Сегмент `task` статический, и с `/tasks/:module/:code` планировщика (`core_monitoring`) он не
// спорит: vue-router ранжирует пути по статичности сегментов, а не по порядку записи, поэтому
// `task` весомее параметра `:module`.
export const tasksRoutes: RouteRecordRaw[] = [
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
