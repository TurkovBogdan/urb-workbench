<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { useDisplay } from 'vuetify'
import { IconChevronRight, IconChevronLeft } from '@tabler/icons-vue'

import { useLayoutStore } from '../store'
import { useSettingsStore } from '@/stores/settings'
import { isGroup, isSection, type NavEntry, type NavLink, type NavSection, type NavSectionEntry } from '@/shared/nav'
import { IconPalette, IconServerCog, IconClock, IconServerBolt, IconTypography, IconInfoCircle, IconStack2, IconChecklist, IconSitemap } from '@tabler/icons-vue'

const layout = useLayoutStore()
const settings = useSettingsStore()
const route  = useRoute()
const { t } = useI18n()
const { mobile } = useDisplay()

// On mobile the drawer is a temporary overlay: never collapse to the rail (always
// full width), toggled via `layout.mobileOpen`. The desktop collapse state is
// ignored while mobile.
const collapsed = computed(() => !mobile.value && settings.ui.sidebarCollapsed)

// Drawer open/close. Desktop permanent drawer is always "open"; mobile overlay
// follows the shared store flag (set by the top-bar hamburger).
const drawerOpen = computed({
  get: () => (mobile.value ? layout.mobileOpen : true),
  set: (v) => { layout.mobileOpen = v },
})

// Navigating closes the overlay (any nav click / programmatic push).
watch(() => route.path, () => { if (mobile.value) layout.mobileOpen = false })

function navLabel(entry: { label: string; labelKey?: string }): string {
  return entry.labelKey ? t(entry.labelKey) : entry.label
}

const navSections: NavSection[] = [
  { kind: 'section', code: 'mcp', labelKey: 'common.nav.mcp', order: 10 },
  // Пространство — общий уровень для прикладных модулей, а не часть какого-то из них, поэтому
  // строка у него своя, выше их всех: ниже идёт то, что внутри пространства и лежит.
  { kind: 'section', code: 'workspace', labelKey: 'common.nav.workspace', order: 15 },
  { kind: 'section', code: 'tasks', labelKey: 'common.nav.tasks', order: 20 },
  { kind: 'section', code: 'settings', labelKey: 'common.nav.settings', order: 50 },
  { kind: 'section', code: 'about', labelKey: 'common.nav.about', order: 60 },
  { kind: 'section', code: 'development', labelKey: 'common.nav.development', order: 70 },
]

const navEntries: NavSectionEntry[] = [
  { section: 'mcp', order: 10, path: '/mcp-servers', label: 'MCP servers', labelKey: 'core_mcp.nav', icon: IconServerBolt },
  { section: 'tasks', order: 10, path: '/tasks/list', label: 'Tasks', labelKey: 'tasks.nav_tasks', icon: IconChecklist },
  { section: 'tasks', order: 20, path: '/tasks/groups', label: 'Groups', labelKey: 'tasks.nav_groups', icon: IconSitemap },
  { section: 'workspace', order: 10, path: '/workspaces', label: 'Workspaces', labelKey: 'workspace.nav', icon: IconStack2 },
  { section: 'settings', order: 10, path: '/settings/interface', label: 'Interface', labelKey: 'settings.interface.nav', icon: IconTypography },
  { section: 'settings', order: 40, path: '/tasks', label: 'Jobs', labelKey: 'core_monitoring.nav', icon: IconClock },
  { section: 'settings', order: 50, path: '/settings/core', label: 'Server', labelKey: 'setup.nav', icon: IconServerCog },
  { section: 'about', order: 10, path: '/about', label: 'Version and update', labelKey: 'about.nav', icon: IconInfoCircle },
  // design-system is template chrome (not a module) — link inlined.
  { section: 'development', order: 10, path: '/design-system', label: 'Design system', labelKey: 'design-system.nav', icon: IconPalette },
]

const navBottom: NavLink[] = []

const byOrder = (a: { order: number }, b: { order: number }) => a.order - b.order

// Раздел без записей не показывается: остался бы висячий заголовок с разделителем.
const visibleNav = computed<NavEntry[]>(() =>
  [...navSections].sort(byOrder).flatMap(section => {
    const sectionEntries = navEntries.filter(entry => entry.section === section.code).sort(byOrder)
    return sectionEntries.length ? [section, ...sectionEntries] : []
  }),
)

const visibleNavBottom = computed<NavLink[]>(() => navBottom)

// Подсветка по ПРЕФИКСУ, а не по точному совпадению: деталка (запуск задачи планировщика —
// `/tasks/<module>/<code>` под записью `/tasks`) принадлежит своему разделу, и раньше на ней в
// меню не было подсвечено ничего.
function isActive(navPath: string) {
  return route.path === navPath || route.path.startsWith(navPath + '/')
}

function isGroupActive(group: NavEntry): boolean {
  return isGroup(group) && group.children.some(c => isActive(c.path))
}

const openGroups = ref<Record<string, boolean>>(
  Object.fromEntries(
    navEntries.filter(isGroup).map(g => [g.label, isGroupActive(g)]),
  ),
)

const drawerWidth = computed(() => (mobile.value ? 280 : collapsed.value ? 56 : 250))
</script>

<template>
  <VNavigationDrawer
    v-model="drawerOpen"
    :permanent="!mobile"
    :temporary="mobile"
    :width="drawerWidth"
    color="surface-variant"
    class="app-sidebar"
    :class="{ 'app-sidebar--collapsed': collapsed }"
  >
    <!-- Шапка панели не прокручивается вместе с меню: логотип и выбор рабочего контекста
         отвечают на вопросы «где я» и «в чём я работаю», и ответ на них не должен уезжать
         вверх вместе со списком разделов. -->
    <template #prepend>
      <!-- Desktop only: brand + rail collapse toggle. On mobile the brand lives in the
           top app-bar (no duplication) and the drawer opens straight to the nav list. -->
      <template v-if="!mobile">
        <div class="sidebar-logo" :class="{ 'sidebar-logo--collapsed': collapsed }">
          <template v-if="!collapsed">
            <RouterLink to="/home" class="logo-link">
              <span class="logo-icon">◈</span>
              <span class="logo-text">Uroboros.Workbench</span>
            </RouterLink>
          </template>
          <VBtn
            :icon="collapsed ? IconChevronRight : IconChevronLeft"
            variant="text"
            density="compact"
            size="small"
            class="collapse-btn"
            @click="settings.ui.sidebarCollapsed = !settings.ui.sidebarCollapsed"
          />
        </div>

        <VDivider class="sidebar-divider" />
      </template>

      <!-- Первый элемент панели — выбор рабочего контекста. Что именно выбирают, панель не
           знает: слой оболочки не тянется в модуль, а получает элемент сверху, из `App.vue`
           (см. conventions/frontend.md — два яруса импорта). Нет слота — нет и полосы: на
           сборке без модуля панель остаётся прежней, без пустой рамки под логотипом. -->
      <template v-if="$slots.context">
        <div class="sidebar-context" :class="{ 'sidebar-context--collapsed': collapsed }">
          <slot name="context" :collapsed="collapsed" />
        </div>

        <VDivider class="sidebar-divider" />
      </template>
    </template>

    <VList
      density="compact"
      nav
      class="sidebar-nav"
      :class="{ 'sidebar-nav--collapsed': collapsed }"
    >
      <!-- ── Collapsed: groups → parent icon + flyout, links → tooltip ── -->
      <template v-if="collapsed">
        <template v-for="(entry, idx) in visibleNav" :key="isSection(entry) ? `s-${idx}` : isGroup(entry) ? entry.label : entry.path">

          <template v-if="isSection(entry)">
            <VDivider
              v-if="idx > 0"
              class="sidebar-section-divider"
            />
          </template>

          <VMenu
            v-else-if="isGroup(entry)"
            location="end"
            :offset="8"
            open-on-click
            close-on-content-click
          >
            <template #activator="{ props }">
              <VListItem
                v-bind="props"
                :active="isGroupActive(entry)"
                :prepend-icon="entry.icon"
                rounded="lg"
                class="nav-item nav-item--collapsed"
              />
            </template>

            <div class="nav-flyout">
              <div class="nav-flyout__title">{{ navLabel(entry) }}</div>
              <VList density="compact" nav class="nav-flyout__list">
                <VListItem
                  v-for="child in entry.children"
                  :key="child.path"
                  :to="child.path"
                  :active="isActive(child.path)"
                  :prepend-icon="child.icon"
                  :title="navLabel(child)"
                  rounded="lg"
                  class="nav-item"
                />
              </VList>
            </div>
          </VMenu>

          <VTooltip
            v-else
            :text="navLabel(entry)"
            location="end"
            :offset="6"
            content-class="sidebar-tooltip"
          >
            <template #activator="{ props }">
              <VListItem
                v-bind="props"
                :to="entry.path"
                :active="isActive(entry.path)"
                :prepend-icon="entry.icon"
                rounded="lg"
                class="nav-item nav-item--collapsed"
              />
            </template>
          </VTooltip>

        </template>
      </template>

      <!-- ── Expanded ── -->
      <template v-else>
        <template v-for="(entry, idx) in visibleNav" :key="isSection(entry) ? `s-${idx}` : isGroup(entry) ? entry.label : entry.path">
          <div
            v-if="isSection(entry)"
            class="nav-section"
          >
            {{ t(entry.labelKey) }}
          </div>

          <VListGroup
            v-else-if="isGroup(entry)"
            v-model="openGroups[entry.label]"
          >
            <template #activator="{ props }">
              <VListItem
                v-bind="props"
                :prepend-icon="entry.icon"
                :title="navLabel(entry)"
                :active="isGroupActive(entry)"
                rounded="lg"
                class="nav-item nav-group-activator"
              />
            </template>

            <VListItem
              v-for="child in entry.children"
              :key="child.path"
              :to="child.path"
              :active="isActive(child.path)"
              :prepend-icon="child.icon"
              :title="navLabel(child)"
              rounded="lg"
              class="nav-item nav-item--child"
            />
          </VListGroup>

          <VListItem
            v-else
            :to="entry.path"
            :active="isActive(entry.path)"
            :prepend-icon="entry.icon"
            :title="navLabel(entry)"
            rounded="lg"
            class="nav-item"
          />
        </template>
      </template>
    </VList>

    <template #append>
      <template v-if="visibleNavBottom.length">
      <VDivider class="sidebar-divider" />
      <VList
        density="compact"
        nav
        class="sidebar-nav pb-2"
        :class="{ 'sidebar-nav--collapsed': collapsed }"
      >
        <VTooltip
          v-for="item in visibleNavBottom"
          :key="item.path"
          :text="navLabel(item)"
          location="end"
          :offset="6"
          :disabled="!collapsed"
          content-class="sidebar-tooltip"
        >
          <template #activator="{ props }">
            <VListItem
              v-bind="props"
              :to="item.path"
              :active="isActive(item.path)"
              :prepend-icon="item.icon"
              :title="collapsed ? '' : navLabel(item)"
              rounded="lg"
              class="nav-item"
              :class="{ 'nav-item--collapsed': collapsed }"
            />
          </template>
        </VTooltip>

      </VList>
      </template>
    </template>
  </VNavigationDrawer>
</template>

<style scoped>
.logo-link {
  flex: 1;
  display: flex;
  align-items: center;
  gap: 10px;
  min-width: 0;
  padding: 0;
  border: 0;
  background: none;
  cursor: pointer;
  text-align: left;
  text-decoration: none;
}

/* Полоса контекста повторяет поля списка разделов (`.sidebar-nav`: 8px, в свёрнутом — 6px):
   элемент стоит над ними одним столбцом, и свои поля увели бы его с их оси. Отбивка снизу
   чуть больше, чем сверху, — линейка под элементом принадлежит ему, а не первому разделу. */
/* Фона у полосы нет: выбор контекста и так отделён от списка разделов линейкой под ним, а
   заливка добавляла к ней вторую границу того же места. */
.sidebar-context {
  padding: 8px 8px 10px;
}

.sidebar-context--collapsed {
  padding: 6px 6px 8px;
}
</style>
