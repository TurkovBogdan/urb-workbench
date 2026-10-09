<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { useDisplay } from 'vuetify'
import { IconChevronRight, IconChevronLeft } from '@tabler/icons-vue'

import { useLayoutStore } from '../store'
import { useSettingsStore } from '@/stores/settings'
import { useAppStore } from '@/stores/app'
import { isGroup, isSection, type NavEntry, type NavLink, type NavSection, type NavSectionEntry } from '@/shared/nav'
import { IconPalette, IconServerCog, IconClock, IconServerBolt, IconTypography, IconInfoCircle, IconChecklist, IconSitemap } from '@tabler/icons-vue'

const layout = useLayoutStore()
const settings = useSettingsStore()
const appStore = useAppStore()
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
  { kind: 'section', code: 'tasks', labelKey: 'common.nav.tasks', order: 20 },
  { kind: 'section', code: 'mcp', labelKey: 'common.nav.mcp', order: 30 },
  { kind: 'section', code: 'settings', labelKey: 'common.nav.settings', order: 50 },
  { kind: 'section', code: 'about', labelKey: 'common.nav.about', order: 60 },
  { kind: 'section', code: 'development', labelKey: 'common.nav.development', order: 70, devOnly: true },
]

const navEntries: NavSectionEntry[] = [
  // The task page is part of the tasks section, even though its address isn't under `/tasks/list`.
  { section: 'tasks', order: 10, path: '/tasks/list', activeOn: ['/tasks/task'], label: 'Tasks', labelKey: 'tasks.nav_tasks', icon: IconChecklist },
  { section: 'tasks', order: 20, path: '/tasks/groups', label: 'Groups', labelKey: 'tasks.nav_groups', icon: IconSitemap },
  { section: 'mcp', order: 10, path: '/mcp-servers', label: 'MCP servers', labelKey: 'core_mcp.nav', icon: IconServerBolt },
  { section: 'settings', order: 10, path: '/settings/interface', label: 'Interface', labelKey: 'settings.interface.nav', icon: IconTypography },
  { section: 'settings', order: 40, path: '/monitoring', label: 'Job monitoring', labelKey: 'core_monitoring.nav', icon: IconClock },
  { section: 'settings', order: 50, path: '/settings/core', label: 'Server', labelKey: 'setup.nav', icon: IconServerCog },
  { section: 'about', order: 10, path: '/about', label: 'Version and update', labelKey: 'about.nav', icon: IconInfoCircle },
  // design-system is template chrome (not a module) — link inlined.
  { section: 'development', order: 10, path: '/design-system', label: 'Design system', labelKey: 'design-system.nav', icon: IconPalette },
]

const navBottom: NavLink[] = []

const byOrder = (a: { order: number }, b: { order: number }) => a.order - b.order

// A section without entries is not shown: a dangling heading with a divider would remain.
const visibleNav = computed<NavEntry[]>(() =>
  [...navSections].filter(section => !section.devOnly || appStore.devMode).sort(byOrder).flatMap(section => {
    const sectionEntries = navEntries.filter(entry => entry.section === section.code).sort(byOrder)
    return sectionEntries.length ? [section, ...sectionEntries] : []
  }),
)

const visibleNavBottom = computed<NavLink[]>(() => navBottom)

// Highlighting by PREFIX, not exact match: a detail page (a scheduler job's runs —
// `/monitoring/<module>/<code>` under the `/monitoring` entry) belongs to its section, and
// previously nothing in the menu was highlighted on it. So item prefixes must not nest inside each
// other: an item at `/tasks` would light up on every page of the tasks module.
function underPrefix(prefix: string): boolean {
  return route.path === prefix || route.path.startsWith(prefix + '/')
}

function isActive(link: NavLink): boolean {
  return underPrefix(link.path) || (link.activeOn ?? []).some(underPrefix)
}

function isGroupActive(group: NavEntry): boolean {
  return isGroup(group) && group.children.some(isActive)
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
    <!-- The sidebar header doesn't scroll with the menu: the logo and the working-context picker
         answer "where am I" and "what am I working in", and those answers must not scroll away
         with the section list. -->
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

      <!-- The first sidebar element is the working-context picker. The sidebar doesn't know what
           exactly is being picked: the shell layer doesn't reach into a module but receives the
           element from above, from `App.vue` (see conventions/frontend.md — two import tiers). No
           slot — no strip: in a build without the module the sidebar stays as it was, without an
           empty frame under the logo. -->
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
                  :active="isActive(child)"
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
                :active="isActive(entry)"
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
              :active="isActive(child)"
              :prepend-icon="child.icon"
              :title="navLabel(child)"
              rounded="lg"
              class="nav-item nav-item--child"
            />
          </VListGroup>

          <VListItem
            v-else
            :to="entry.path"
            :active="isActive(entry)"
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
              :active="isActive(item)"
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

/* The context strip mirrors the section list padding (`.sidebar-nav`: 8px, collapsed — 6px): the
   element stands above them in one column, and its own padding would pull it off their axis. The
   bottom spacing is slightly larger than the top — the rule under the element belongs to it, not
   to the first section. */
/* The strip has no background: the context picker is already separated from the section list by
   the rule under it, and a fill added a second border at the same spot. */
.sidebar-context {
  padding: 8px 8px 10px;
}

.sidebar-context--collapsed {
  padding: 6px 6px 8px;
}</style>
