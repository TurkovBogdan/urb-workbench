<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'

// Table cell for members: shows the first one and hides the rest behind a "+N" chip, which
// on click opens a tooltip popup with the full list. Each item is clickable — the component
// emits `select` with the index, and the parent picks the action (filter by contact, by team
// member, etc.). The pattern comes from the original chats list.
export interface MemberCellItem {
  // Primary label (name or email).
  label: string
  // Secondary line in the popup (email/phone); shown only if it differs from label.
  sub?: string | null
  // Non-clickable item (nothing to filter by) — the title is visible, no click is emitted.
  disabled?: boolean
}

const props = withDefaults(defineProps<{
  items: MemberCellItem[]
  // Label for an empty cell (no members).
  emptyText?: string
  // Italic, muted empty label (e.g. "No team").
  emptyItalic?: boolean
  // Popup title; defaults to the shared hint "Click to apply the filter".
  hint?: string
  // Monospace label text (for email columns).
  mono?: boolean
  // Truncation length of the visible label.
  max?: number
}>(), {
  emptyText: '—',
  emptyItalic: false,
  mono: false,
  max: 32,
})

const emit = defineEmits<{ (e: 'select', index: number): void }>()

const { t } = useI18n()

const hintText = computed(() => props.hint ?? t('common.members_cell.hint'))
const first = computed(() => props.items[0])
const extra = computed(() => props.items.length - 1)

function truncate(value: string): string {
  return value.length > props.max ? value.slice(0, props.max).trimEnd() + '…' : value
}

function pick(index: number): void {
  if (props.items[index]?.disabled) return
  emit('select', index)
}
</script>

<template>
  <div class="members-cell">
    <template v-if="first">
      <a
        v-if="!first.disabled"
        class="members-cell__link"
        :class="{ 'members-cell--mono': mono }"
        :title="first.sub || first.label"
        @click.stop="pick(0)"
      >{{ truncate(first.label) }}</a>
      <span
        v-else
        class="members-cell__plain"
        :class="{ 'members-cell--mono': mono }"
        :title="first.label"
      >{{ truncate(first.label) }}</span>

      <VMenu
        v-if="extra > 0"
        location="bottom start"
        offset="8"
        content-class="members-cell-menu"
        :close-on-content-click="true"
      >
        <template #activator="{ props: menuProps }">
          <VChip
            v-bind="menuProps"
            size="x-small"
            variant="tonal"
            color="primary"
            class="members-cell__more"
            @click.stop
          >
            +{{ extra }}
          </VChip>
        </template>
        <div class="members-popover">
          <div class="members-popover__hint">{{ hintText }}</div>
          <VList density="compact" class="members-popover__list">
            <VListItem
              v-for="(m, i) in items"
              :key="i"
              :disabled="m.disabled"
              @click.stop="pick(i)"
            >
              <VListItemTitle class="members-popover__name" :class="{ 'members-cell--mono': mono }">{{ m.label }}</VListItemTitle>
              <VListItemSubtitle
                v-if="m.sub && m.sub !== m.label"
                class="members-popover__sub"
                :class="{ 'members-cell--mono': mono }"
              >{{ m.sub }}</VListItemSubtitle>
            </VListItem>
          </VList>
        </div>
      </VMenu>
    </template>

    <span
      v-else
      class="members-cell__empty"
      :class="{ 'members-cell__empty--italic': emptyItalic }"
    >{{ emptyText }}</span>
  </div>
</template>

<style scoped>
.members-cell {
  display: flex;
  align-items: center;
  gap: 6px;
  min-width: 0;
}

.members-cell__link {
  font-size: 12px;
  color: var(--accent, rgb(var(--v-theme-primary)));
  cursor: pointer;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.members-cell__link:hover { text-decoration: underline; }

.members-cell__plain {
  font-size: 12px;
  color: var(--text-muted);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.members-cell__empty { color: var(--text-faint); }
.members-cell__empty--italic { font-style: italic; }

.members-cell__more {
  cursor: pointer;
  flex: 0 0 auto;
  transition: background-color .15s ease, color .15s ease;
}

.members-cell__more:hover {
  background: var(--accent);
  color: #fff;
}

.members-cell--mono { font-family: var(--font-mono); }

/* ── Popover (tooltip bubble with an arrow) ─────────────────────────── */

.members-popover {
  position: relative;
  min-width: 220px;
  max-width: 380px;
  overflow: visible;
  background: rgb(var(--v-theme-surface));
  border: 1px solid var(--border-soft);
  border-radius: 8px;
  /* drop-shadow (not box-shadow): the shadow follows the outline including the arrow pseudo-element. */
  filter: drop-shadow(0 6px 18px rgb(0 0 0 / 14%));
}

/* The arrow: a rotated square at the top edge, under the activator (location=bottom start).
   Its top and left edges carry the border — that is the tip above the popup's top border. */
.members-popover::before {
  content: '';
  position: absolute;
  top: -6px;
  left: 16px;
  width: 10px;
  height: 10px;
  background: rgb(var(--v-theme-surface));
  border-top: 1px solid var(--border-soft);
  border-left: 1px solid var(--border-soft);
  transform: rotate(45deg);
}

.members-popover__hint {
  padding: 8px 14px;
  font-size: 11px;
  font-weight: 500;
  color: var(--text-muted);
  border-bottom: 1px solid var(--border-soft);
  border-radius: 7px 7px 0 0;
}

.members-popover__list {
  background: transparent;
  padding: 4px 6px 6px;
  max-height: 320px;
  overflow-y: auto;
  border-radius: 0 0 7px 7px;
}

.members-popover__name {
  font-size: 13px;
  color: var(--text);
}

.members-popover__sub {
  font-size: 12px;
  color: var(--text-faint);
}
</style>

<!-- Menu content is teleported outside the component, so these overrides can't be scoped —
     keep them global, namespaced by the menu's content-class. The inner `.v-list` otherwise
     inherits the global dropdown-card styling (surface bg + border + shadow), stacking a
     second panel inside `.members-popover`; the extra `.v-list` qualifier outscores that
     rule so the list stays flat. -->
<style>
.members-cell-menu.v-overlay__content { overflow: visible; }

.v-menu .members-cell-menu .members-popover__list.v-list {
  background: transparent;
  border: none;
  border-radius: 0;
  box-shadow: none;
}

/* Brand (primary) item highlight on hover — the default overlay is grey (on-surface). */
.members-cell-menu .v-list-item--link:hover > .v-list-item__overlay {
  background: rgb(var(--v-theme-primary));
}
</style>
