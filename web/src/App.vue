<script setup lang="ts">
import { computed } from 'vue'
import { useRoute } from 'vue-router'
import { useDisplay } from 'vuetify'
import { IconMenu2, IconX } from '@tabler/icons-vue'
import AppSidebar from '@/layout/components/AppSidebar.vue'
import ErrorScreen from '@/components/ErrorScreen.vue'
import ToastStack from '@/components/ToastStack.vue'
import { navigationLoading } from '@/router/progress'
import { endRouteTransition } from '@/composables/useRouteTransition'
import { shellError } from '@/composables/useShellError'
import { useLayoutStore } from '@/layout/store'
// The shell assembles the modules — the sidebar doesn't know them: the workspace switcher arrives
// in its slot from here, just as module routes arrive in the router (see conventions/frontend.md —
// two import tiers).
import WorkspaceSwitcher from '@/features/workspace/components/WorkspaceSwitcher.vue'
import ChangesIndicator from '@/layout/components/ChangesIndicator.vue'

const route = useRoute()
const { mobile } = useDisplay()
const layout = useLayoutStore()

const fullscreen = computed(() => route.meta.fullscreen === true)

// Content-zone transition, overridable per-route via `meta.transition`. Bound to the
// destination route's meta, so both the leave and enter use the incoming route's name.
// A name with no matching CSS (e.g. 'none') renders instantly.
const transitionName = computed(() => route.meta.transition ?? 'page')
</script>

<template>
  <VApp>
    <!-- Mobile top bar: hamburger toggles the overlay drawer, brand → home.
         Hidden on desktop (permanent rail) and on fullscreen routes (404). -->
    <VAppBar
      v-if="mobile && !fullscreen"
      class="app-topbar"
      flat
      height="54"
    >
      <!-- Toggles the overlay drawer; the glyph flips to a close (X) while open. -->
      <VBtn
        :icon="layout.mobileOpen ? IconX : IconMenu2"
        variant="text"
        density="comfortable"
        class="app-topbar__menu"
        @click="layout.mobileOpen = !layout.mobileOpen"
      />
      <RouterLink to="/home" class="app-topbar__brand">
        <span class="logo-icon">◈</span>
        <span class="logo-text">Uroboros.Workbench</span>
      </RouterLink>
      <VSpacer />
    </VAppBar>

    <AppSidebar v-if="!fullscreen">
      <template #context="{ collapsed }">
        <WorkspaceSwitcher :collapsed="collapsed" />
      </template>
    </AppSidebar>
    <VMain class="main-content">
      <!-- Navigation loading bar — pinned to the top of the content zone, right of
           the sidebar. Driven by the router guards (router/progress.ts); fades in
           only when a hop crosses the show-delay (e.g. a lazy chunk download). -->
      <Transition name="route-progress">
        <VProgressLinear
          v-if="navigationLoading"
          class="route-progress"
          indeterminate
          color="primary"
          height="3"
        />
      </Transition>
      <!-- Transition wraps the content zone only — the sidebar lives outside
           RouterView, so it never animates. `out-in` keeps a single page in the
           layout at a time (no two full-height pages overlapping). `appear` runs
           the enter once on first paint (after the boot splash). Order must be
           Transition > KeepAlive > component. -->
      <!-- A failure that leaves nothing to look at on the route is drawn INSTEAD of the content
           and at the same address: redirecting to a separate `/403` would erase the only clue —
           what the person had opened. The next navigation clears it (router guard). -->
      <ErrorScreen v-if="shellError" :kind="shellError" class="h-100" />
      <!-- The end of the enter is the only moment the animation is known to have played out:
           until then pages hold back heavy content (useRouteTransition). A cancelled enter
           (the next navigation overtook the animation) counts as the same end — waiting for a
           transition that no longer exists is not an option. -->
      <RouterView v-else v-slot="{ Component }">
        <Transition
          :name="transitionName"
          mode="out-in"
          appear
          @after-enter="endRouteTransition"
          @enter-cancelled="endRouteTransition"
        >
          <KeepAlive>
            <component :is="Component" class="h-100" />
          </KeepAlive>
        </Transition>
      </RouterView>
    </VMain>

    <!-- A failure the screen didn't show itself surfaces here: a message on top of everything,
         outside the content zone, so it survives a route change. -->
    <ToastStack />

    <!-- The change feed's quiet signal: what changed in the data — small, in the corner, for a couple of seconds. -->
    <ChangesIndicator v-if="!fullscreen" />
  </VApp>
</template>

<style scoped>
/* ── Mobile top bar ─────────────────────────────────────────────────────── */
.app-topbar {
  background: var(--sidebar-bg);
  border-bottom: 1px solid var(--border-soft);
  box-shadow: none;
}
.app-topbar :deep(.v-toolbar__content) {
  padding-inline: 8px;
  gap: 4px;
}
/* Specific enough to outweigh main.scss's text-button color, hover included. */
.app-topbar .app-topbar__menu.v-btn {
  color: var(--text-muted);
}
.app-topbar__brand {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 4px 6px;
  border: 0;
  background: none;
  cursor: pointer;
  border-radius: var(--radius-sm);
  text-decoration: none;
  .logo-icon { font-size: 18px; color: var(--accent); line-height: 1; }
  .logo-text { font-size: 14px; font-weight: 600; color: var(--text); letter-spacing: -0.01em; white-space: nowrap; }
}

/* Overlay at the very top of the content zone — does not push the page down. */
.route-progress {
  position: absolute;
  inset: 0 0 auto 0;
  z-index: 6;
}

/* Fade the bar itself in/out so it never pops. */
.route-progress-enter-active,
.route-progress-leave-active {
  transition: opacity 0.2s ease;
}
.route-progress-enter-from,
.route-progress-leave-to {
  opacity: 0;
}
</style>
