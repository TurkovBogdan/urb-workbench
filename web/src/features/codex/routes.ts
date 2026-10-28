import type { RouteRecordRaw } from 'vue-router'

import { CODEX_AVAILABLE, CODEX_MATERIALS } from './paths'

// The codex section (TEST IMPLEMENTATION, TASK@8EAB179834): the materials — the canvas of the
// current workspace and its editor, one address for a codex and a note since they share the CODEX@
// prefix (the page `interface_open(CODEX@…)` opens) — and the available codexes, every one of them.
export const codexRoutes: RouteRecordRaw[] = [
  { path: '/codex', redirect: CODEX_MATERIALS },
  // A record alone on a sheet, outside the app's frame: the "PDF" button prints this address in a
  // hidden frame. Two segments after the materials, so the editor's optional one never takes it.
  {
    path: `${CODEX_MATERIALS}/:code/print`,
    name: 'codex-print',
    component: () => import('./views/CodexPrintView.vue'),
    meta: { scroll: 'none', fullscreen: true, transition: 'none', title: 'common.print.title' },
  },
  {
    path: `${CODEX_MATERIALS}/:code?`,
    name: 'codex-editor',
    component: () => import('./views/CodexEditorView.vue'),
    meta: { scroll: 'y', title: 'codex.nav_materials' },
  },
  {
    path: CODEX_AVAILABLE,
    name: 'codex-list',
    component: () => import('./views/CodexListView.vue'),
    // The page's full name, not the menu's short "Manage": a tab title stands without its section.
    meta: { scroll: 'y', title: 'codex.list.title' },
  },
]
