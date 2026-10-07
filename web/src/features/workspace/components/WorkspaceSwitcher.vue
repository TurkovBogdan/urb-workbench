<script setup lang="ts">
// Picking the current workspace — the first element of the sidebar.
//
// A workspace is a CONTEXT, not a place: switching it opens nothing and leads nowhere, it only
// answers the question "what am I working in right now".
//
// The button is a context card rather than a field or a menu row: a frameless row of the same
// metrics as the items below read as one more section, and an outlined select read as a form input
// dropped into the navigation.
//
// The panel is a widget of its own on `VMenu`, not a `VSelect`: it needs a search that keeps the
// keyboard (↑/↓/Enter while the caret stays in the query), and a footer with actions — neither has
// a place in a select's item list. Both sidebar states open the same panel; collapsed, only the
// badge is left of the button.
//
// The panel is also the way into managing workspaces: the "Workspaces" section left the
// navigation, so the footer links the page and creates a workspace in place.
//
// The set loads itself: the place of use need not know whether someone loaded workspaces before.
import { computed, onMounted, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { IconCheck, IconPlus, IconSearch, IconSelector, IconSettings, IconStack2 } from '@tabler/icons-vue'

import IconSwatch from '@/components/IconSwatch.vue'
import { useWorkspaceContextStore } from '../stores/workspace-context.store'
import WorkspaceFormDialog from './WorkspaceFormDialog.vue'

const props = withDefaults(defineProps<{
  /** The sidebar is collapsed into a rail: only the current workspace's badge is visible. */
  collapsed?: boolean
}>(), {
  collapsed: false,
})

const { t } = useI18n()
const store = useWorkspaceContextStore()

onMounted(store.ensure)

// The placeholder shows only when emptiness is certain: before the backend answers, an invitation
// to create the first workspace would appear while existing ones are alive.
const noWorkspaces = computed(() => store.isEmpty)

const open = ref(false)
const query = ref('')
const highlighted = ref(0)
const formOpen = ref(false)
const searchInput = ref<HTMLInputElement | null>(null)
const listEl = ref<HTMLElement | null>(null)

// Only the title is searched: it is all a row shows, and a match on hidden text would surface a row
// with nothing in it to explain why. JS case folding is Unicode-aware, so Cyrillic matches either
// case.
const matches = computed(() => {
  const needle = query.value.trim().toLowerCase()
  if (!needle) return store.items
  return store.items.filter((workspace) => workspace.title.toLowerCase().includes(needle))
})

// Without a query the walk starts from the current workspace — the arrows then step to its
// neighbours; with one, from the best match at the top.
function resetHighlight(): void {
  highlighted.value = query.value.trim()
    ? 0
    : Math.max(0, matches.value.findIndex((workspace) => workspace.code === store.current))
}

watch(open, (isOpen) => {
  if (!isOpen) return
  query.value = ''
  resetHighlight()
  void store.refresh()
})

watch(query, resetHighlight)

// Focus goes to the query only once the menu has finished entering: earlier, the overlay's own
// focus handling takes it back to the panel root.
function focusSearch(): void {
  searchInput.value?.focus()
}

function move(step: number): void {
  const count = matches.value.length
  if (!count) return
  highlighted.value = (highlighted.value + step + count) % count
  listEl.value?.children[highlighted.value]?.scrollIntoView({ block: 'nearest' })
}

function choose(code: string): void {
  store.select(code)
  open.value = false
}

function chooseHighlighted(): void {
  const workspace = matches.value[highlighted.value]
  if (workspace) choose(workspace.code)
}

function startCreate(): void {
  open.value = false
  formOpen.value = true
}

// Creating from the switcher means wanting to work there: the new workspace becomes current. The
// dialog reports no code, so the new one is the code the fresh set has and the old one did not.
async function onCreated(): Promise<void> {
  const known = new Set(store.items.map((workspace) => workspace.code))
  await store.refresh()
  const created = store.items.find((workspace) => !known.has(workspace.code))
  if (created) store.select(created.code)
}
</script>

<template>
  <!-- ── No workspaces: instead of a choice — the way to create the first one ── -->
  <template v-if="noWorkspaces">
    <VTooltip
      v-if="props.collapsed"
      :text="t('workspace.switcher.empty_action')"
      location="end"
      :offset="6"
      content-class="sidebar-tooltip"
    >
      <template #activator="{ props: tip }">
        <button v-bind="tip" type="button" class="ws-rail ws-rail--empty" @click="formOpen = true">
          <IconPlus :size="18" :stroke-width="1.7" />
        </button>
      </template>
    </VTooltip>

    <button v-else type="button" class="ws-empty" @click="formOpen = true">
      <IconStack2 :size="18" :stroke-width="1.6" class="ws-empty__icon" />
      <span class="ws-empty__text">
        <span class="ws-empty__title">{{ t('workspace.switcher.empty') }}</span>
        <span class="ws-empty__action">{{ t('workspace.switcher.empty_action') }}</span>
      </span>
    </button>
  </template>

  <!-- ── Something to choose from: the context card and the panel ── -->
  <VMenu
    v-else
    v-model="open"
    :location="props.collapsed ? 'end top' : 'bottom start'"
    :offset="props.collapsed ? 8 : 6"
    :close-on-content-click="false"
    @after-enter="focusSearch"
  >
    <template #activator="{ props: menu }">
      <button
        v-bind="menu"
        type="button"
        :class="props.collapsed ? 'ws-rail' : 'ws-card'"
        :aria-label="t('workspace.switcher.label')"
      >
        <IconSwatch
          v-if="store.currentWorkspace"
          :icon="store.currentWorkspace.icon"
          :color="store.currentWorkspace.color"
          :width="28"
        />
        <IconStack2 v-else :size="18" :stroke-width="1.7" />

        <template v-if="!props.collapsed">
          <span class="ws-card__title">{{ store.currentWorkspace?.title }}</span>
          <IconSelector :size="16" :stroke-width="1.7" class="ws-card__caret" />
        </template>
      </button>
    </template>

    <div
      class="ws-panel"
      @keydown.down.prevent="move(1)"
      @keydown.up.prevent="move(-1)"
      @keydown.enter.prevent="chooseHighlighted"
    >
      <label class="ws-panel__search">
        <IconSearch :size="16" :stroke-width="1.7" class="ws-panel__search-icon" />
        <input
          ref="searchInput"
          v-model="query"
          type="text"
          class="ws-panel__input"
          :placeholder="t('workspace.switcher.search')"
          :aria-label="t('workspace.switcher.search')"
          autocomplete="off"
          spellcheck="false"
        >
      </label>

      <!-- Options are out of the Tab order: the list is walked with the arrows from the query, and
           Tab goes on to the footer actions. -->
      <div
        v-if="matches.length"
        ref="listEl"
        class="ws-panel__list"
        role="listbox"
        :aria-label="t('workspace.switcher.label')"
      >
        <button
          v-for="(workspace, index) in matches"
          :key="workspace.code"
          type="button"
          role="option"
          tabindex="-1"
          :aria-selected="workspace.code === store.current"
          class="ws-option"
          :class="{
            'ws-option--highlighted': index === highlighted,
            'ws-option--current': workspace.code === store.current,
          }"
          @mouseenter="highlighted = index"
          @click="choose(workspace.code)"
        >
          <IconSwatch :icon="workspace.icon" :color="workspace.color" :width="24" />
          <span class="ws-option__title">{{ workspace.title }}</span>
          <IconCheck
            v-if="workspace.code === store.current"
            :size="16"
            :stroke-width="2"
            class="ws-option__check"
          />
        </button>
      </div>
      <div v-else class="ws-panel__empty">{{ t('workspace.switcher.not_found') }}</div>

      <div class="ws-panel__footer">
        <button type="button" class="ws-action" @click="startCreate">
          <IconPlus :size="16" :stroke-width="1.7" />
          {{ t('workspace.switcher.create') }}
        </button>
        <RouterLink to="/workspaces" class="ws-action" @click="open = false">
          <IconSettings :size="16" :stroke-width="1.7" />
          {{ t('workspace.switcher.manage') }}
        </RouterLink>
      </div>
    </div>
  </VMenu>

  <WorkspaceFormDialog v-model="formOpen" :workspace="null" @saved="onCreated" />
</template>

<style scoped>
/* ── Context card (expanded sidebar) ────────────────────────────────────────── */
/* No fill and no padding of its own: the rule under the strip already separates the card from the
   section list, and a fill read as a second border at the same spot. Hover answers on the chevron,
   since without a box there is no edge to light. */
.ws-card {
  display: flex;
  align-items: center;
  gap: 10px;
  width: 100%;
  padding: 0;
  border: 0;
  border-radius: var(--radius-sm);
  background: none;
  color: var(--text);
  cursor: pointer;
  text-align: left;
}

.ws-card:hover .ws-card__caret,
.ws-card[aria-expanded='true'] .ws-card__caret {
  color: var(--text);
}

.ws-card:focus-visible {
  outline: 2px solid var(--accent);
  outline-offset: 1px;
}

.ws-card__title {
  flex: 1;
  min-width: 0;
  font-size: 13px;
  font-weight: 600;
  line-height: 18px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

/* The chevron is muted: it says the panel will open, but has no reason to compete with the name. */
.ws-card__caret {
  flex: none;
  color: var(--text-faint);
  transition: color 0.15s;
}

/* ── Collapsed rail ─────────────────────────────────────────────────────────── */
/* The box mirrors a rail menu item (`.nav-item--collapsed`): the element stands in one column
   with them, and its own width would pull its icon off the shared axis. */
.ws-rail {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 100%;
  min-height: 40px;
  border: 0;
  background: none;
  border-radius: var(--radius-sm);
  color: var(--text-muted);
  cursor: pointer;
  transition: background-color 0.15s, color 0.15s;
}

.ws-rail:hover,
.ws-rail[aria-expanded='true'] {
  background-color: var(--surface-hi);
  color: var(--text);
}

/* The rail placeholder is the same box but with a border: otherwise the empty spot under the
   badge reads as "failed to load" rather than "nothing created yet". */
.ws-rail--empty {
  border: 1px dashed var(--border);
}

/* ── Panel ──────────────────────────────────────────────────────────────────── */
/* Wider than the sidebar on purpose: long titles get room the card does not have. */
.ws-panel {
  display: flex;
  flex-direction: column;
  width: 300px;
  background: var(--legacy-flyout-bg);
  border: 1px solid var(--border-soft);
  border-radius: var(--radius);
  box-shadow: 0 8px 24px rgba(0, 0, 0, 0.12);
  overflow: hidden;
}

.ws-panel__search {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 10px 12px;
  border-bottom: 1px solid var(--border-soft);
  cursor: text;
}

.ws-panel__search-icon {
  flex: none;
  color: var(--text-faint);
}

.ws-panel__input {
  flex: 1;
  min-width: 0;
  border: 0;
  outline: none;
  background: none;
  color: var(--text);
  font: inherit;
  font-size: 13px;
}

.ws-panel__input::placeholder {
  color: var(--text-faint);
}

.ws-panel__list {
  display: flex;
  flex-direction: column;
  gap: 2px;
  max-height: 320px;
  padding: 6px;
  overflow-y: auto;
}

.ws-panel__empty {
  padding: 14px 12px;
  font-size: 12px;
  color: var(--text-faint);
  text-align: center;
}

.ws-panel__footer {
  display: flex;
  flex-direction: column;
  padding: 6px;
  border-top: 1px solid var(--border-soft);
}

/* ── Panel rows ─────────────────────────────────────────────────────────────── */
/* One highlight source — the keyboard index, which the pointer moves on hover: a separate :hover
   would light a second row while the arrows walk the first. */
.ws-option {
  display: flex;
  align-items: center;
  gap: 10px;
  width: 100%;
  padding: 6px 8px;
  border: 0;
  border-radius: var(--radius-sm);
  background: none;
  color: var(--text);
  cursor: pointer;
  text-align: left;
}

.ws-option--highlighted {
  background-color: var(--surface-hi);
}

.ws-option__title {
  flex: 1;
  min-width: 0;
  font-size: 13px;
  line-height: 18px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.ws-option--current .ws-option__title {
  font-weight: 600;
}

.ws-option__check {
  flex: none;
  color: var(--accent);
}

.ws-action {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 7px 8px;
  border: 0;
  border-radius: var(--radius-sm);
  background: none;
  color: var(--text-muted);
  font-size: 13px;
  text-align: left;
  text-decoration: none;
  cursor: pointer;
  transition: background-color 0.15s, color 0.15s;
}

.ws-action:hover,
.ws-action:focus-visible {
  background-color: var(--surface-hi);
  color: var(--text);
  outline: none;
}

/* ── Placeholder in the expanded sidebar ────────────────────────────────────── */
.ws-empty {
  display: flex;
  align-items: center;
  gap: 10px;
  width: 100%;
  padding: 8px 10px;
  border: 1px dashed var(--border);
  border-radius: var(--radius-sm);
  background: none;
  color: var(--text-muted);
  cursor: pointer;
  text-align: left;
  transition: border-color 0.15s, color 0.15s;
}

.ws-empty:hover {
  border-color: var(--accent);
  color: var(--text);
}

.ws-empty__icon {
  flex: none;
}

.ws-empty__text {
  display: flex;
  flex-direction: column;
  min-width: 0;
}

.ws-empty__title {
  font-size: 12px;
  font-weight: 500;
  color: var(--text);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

/* The invitation is a second line, not a button beside it: the whole panel is the button, and a
   button inside it would be a second way to do the same thing. */
.ws-empty__action {
  font-size: 11px;
  color: var(--accent);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
</style>
