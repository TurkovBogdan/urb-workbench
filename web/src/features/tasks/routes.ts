import type { RouteRecordRaw } from 'vue-router'

// Раздел модуля задач: список, группы и деталка задачи. Пространства уехали в свой модуль
// (`features/workspace/routes.ts`).
//
// Задача живёт СТРАНИЦЕЙ по собственному адресу, а не окном поверх списка: в ней работают —
// правят текст, водят статус, ходят по ветке подзадач, — и всё это требует места и своей записи
// в истории переходов.
export const tasksRoutes: RouteRecordRaw[] = [
  // Корень раздела — список. Раньше на `/tasks` жил мониторинг планировщика (теперь `/monitoring`),
  // и старая ссылка не должна упираться в «страница не найдена».
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
