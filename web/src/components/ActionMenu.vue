<script lang="ts">
import type { TablerIcon } from '@/shared/nav'

/** One item of the menu: the menu draws it, runs it, and puts it on its key. */
export interface ActionMenuItem {
  /** Unique within the menu. */
  key: string
  icon: TablerIcon
  label: string
  run: () => void
  /** The item costs something — deleting, purging — and says so in color. */
  danger?: boolean
  disabled?: boolean
  /**
   * The key that runs the item while the menu is open, as written on it: a Latin letter by the
   * action's meaning — `E` edit, `D` delete, `C` cancel — or a digit where one was asked for
   * explicitly. It stands next to the item.
   */
  hotkey?: string
  /** The item opens a new block: a divider goes above it. */
  divider?: boolean
}
</script>

<script setup lang="ts">
// The action menu of a list entry — a task row, a group card, a workspace row: one for the whole
// app, so that it opens, closes and answers keys the same way wherever there is a "⋯".
//
// It opens from its "⋯" and, through `openAt`, on a right click anywhere on the entry; how it
// is pinned and what closes it is `usePointerMenu`. `v-model:open` is for the entry: while the
// menu is open the pointer has left for the items, and only the entry's own mark still says which
// one the actions will hit.
//
// KEYS ARE A PROPERTY OF THE ITEM, not a handler next to the menu: the key drawn by an item and
// the key that runs it come from the same field and cannot drift apart. Matched by `code`, not by
// the character, so `E` works in the Russian layout too and a digit works on the keypad.
import { onBeforeUnmount, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { IconCheck, IconCopy, IconDotsVertical } from '@tabler/icons-vue'

import KeyCap from '@/components/KeyCap.vue'
import { useClipboard } from '@/composables/useClipboard'
import { usePointerMenu } from '@/composables/usePointerMenu'

const props = defineProps<{
  items: ActionMenuItem[]
  /** What the "⋯" is called — for the tooltip and a screen reader. */
  label: string
  /**
   * The code the agent knows the entity by. Given — the menu opens with "Copy code": every entry
   * that has a code is named to the agent by it, a deleted one included.
   */
  code?: string
}>()

const open = defineModel<boolean>('open', { default: false })

const { t } = useI18n()

const root = ref<HTMLElement>()
const overlay = ref<{ contentEl?: HTMLElement }>()
const { openAt, fromButton, placement } = usePointerMenu(
  (target) => !!(overlay.value?.contentEl?.contains(target) || root.value?.contains(target)),
  open,
)

// The menu would close on the click and take the check mark with it — so the item holds the menu
// open just long enough for the check to be seen, then closes it itself.
const COPIED_MARK_MS = 700
const { copy, isCopied } = useClipboard()

async function copyCode(code: string) {
  await copy(code)
  setTimeout(() => { open.value = false }, COPIED_MARK_MS)
}

const HOTKEY = /^(?:Key([A-Z])|(?:Digit|Numpad)([1-9]))$/

function runHotkey(event: KeyboardEvent) {
  if (event.ctrlKey || event.metaKey || event.altKey || event.shiftKey || event.repeat) return
  const match = HOTKEY.exec(event.code)
  const key = match?.[1] ?? match?.[2]
  const item = key && props.items.find((candidate) => candidate.hotkey === key)
  if (!item || item.disabled) return
  event.preventDefault()
  open.value = false
  item.run()
}

watch(open, (isOpen) => {
  if (isOpen) window.addEventListener('keydown', runHotkey)
  else window.removeEventListener('keydown', runHotkey)
})

onBeforeUnmount(() => window.removeEventListener('keydown', runHotkey))

defineExpose({ openAt })
</script>

<template>
  <!-- A control, not part of the entry: a click on the "⋯" must not also open what it sits on. -->
  <span ref="root" class="action-menu" @click.stop>
    <VMenu ref="overlay" v-model="open" v-bind="placement">
      <template #activator="{ props: activator }">
        <VBtn
          v-bind="activator"
          icon
          variant="text"
          class="action-menu__button"
          :title="props.label"
          :aria-label="props.label"
          @click="fromButton"
        >
          <IconDotsVertical :size="16" :stroke-width="1.6" />
        </VBtn>
      </template>

      <!-- A right click on the menu itself does nothing: the browser's own menu would open on top
           of ours and hide it. -->
      <VList density="compact" @contextmenu.prevent>
        <!-- `.stop` keeps the click from the menu's content: that click would close it at once. -->
        <VListItem
          v-if="props.code"
          :prepend-icon="isCopied(props.code) ? IconCheck : IconCopy"
          @click.stop="copyCode(props.code)"
        >
          <VListItemTitle>{{ t('common.action.copy_code') }}</VListItemTitle>
        </VListItem>
        <template v-for="item in props.items" :key="item.key">
          <VDivider v-if="item.divider" class="my-1" />
          <VListItem
            :prepend-icon="item.icon"
            :disabled="item.disabled"
            :class="{ 'action-menu__item--danger': item.danger }"
            @click="item.run()"
          >
            <VListItemTitle>{{ item.label }}</VListItemTitle>
            <template v-if="item.hotkey" #append>
              <KeyCap class="action-menu__key" :label="item.hotkey" />
            </template>
          </VListItem>
        </template>
      </VList>
    </VMenu>
  </span>
</template>

<style scoped>
.action-menu {
  display: inline-flex;
  flex: none;
}

/* The box is set here, not via `size`/`density`: for an icon button Vuetify computes the side as
   `--v-btn-height + 12px`. The color is the entry's: it decides how loud its "⋯" is. */
.action-menu__button {
  width: 28px;
  min-width: 28px;
  height: 28px;
  color: inherit;
}

.action-menu__item--danger :deep(.v-list-item-title),
.action-menu__item--danger :deep(.v-list-item__prepend) { color: var(--error); }

/* The key that runs the item, set apart from the item's name. */
.action-menu__key { margin-left: 16px; }
</style>
