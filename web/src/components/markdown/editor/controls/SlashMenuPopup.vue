<script setup lang="ts">
// The popup half of the slash menu. Plain Vuetify: the menu inherits the application's theme,
// density and focus styling because it is made of the same parts as the rest of the interface.
import { computed, nextTick, ref, watch } from 'vue'
import KeyCap from '@/components/KeyCap.vue'
import { shortcutLabels } from './slashMenu'
import type { SlashController, SlashState } from './slashMenu'

const props = defineProps<{ state: SlashState; controller: SlashController }>()

const MENU_HEIGHT = 320

const scroller = ref<HTMLElement | null>(null)

// Keep the active item in view. Keyboard navigation moves the choice past the bottom edge of the
// list, and without this the person presses the arrow into the void: the highlight has gone where
// it cannot be seen. `block: 'nearest'` scrolls just enough to reveal the item and does not jerk
// the list when it is already on screen.
watch(() => props.state.active, async (index) => {
  await nextTick()
  scroller.value?.querySelector(`[data-index="${index}"]`)?.scrollIntoView({ block: 'nearest' })
})

// A new query means a different list: scroll back to the top, otherwise the first item ends up
// above the visible area.
watch(() => props.state.items, async () => {
  await nextTick()
  if (scroller.value) scroller.value.scrollTop = 0
})

// Flip above the caret near the bottom of the viewport. `position: fixed` puts the menu
// outside the editor's scroll box, so it never clips against the page column.
const above = computed(() => props.state.top + MENU_HEIGHT > window.innerHeight)

const style = computed(() => ({
  left: `${props.state.left}px`,
  ...(above.value
    ? { bottom: `${window.innerHeight - props.state.bottom + 6}px` }
    : { top: `${props.state.top + 6}px` }),
}))
</script>

<template>
  <Teleport to="body">
    <div v-if="state.open && state.items.length" class="slash" :style="style">
      <VCard elevation="8" rounded="lg" class="slash__card">
        <div ref="scroller" class="slash__scroll">
          <VList density="compact" nav class="py-1">
            <template v-for="(item, index) in state.items" :key="item.id">
              <!-- A rule between groups: block types read as separate sets rather than one long
                   sheet. Drawn before the first item of every group except the very first. -->
              <VDivider v-if="index > 0 && item.group !== state.items[index - 1].group" class="my-1" />
              <VListItem
                :data-index="index"
                :active="index === state.active"
                color="primary"
                @click="controller.pick(index)"
              >
                <template #prepend>
                  <component :is="item.icon" :size="17" class="slash__icon" />
                </template>
                <VListItemTitle class="slash__title">{{ item.title }}</VListItemTitle>
                <template #append>
                  <span v-if="item.keys" class="slash__keys">
                    <KeyCap v-for="key in shortcutLabels(item.keys)" :key="key" :label="key" />
                  </span>
                </template>
              </VListItem>
            </template>
          </VList>
        </div>
      </VCard>
    </div>
  </Teleport>
</template>

<style scoped>
.slash {
  position: fixed;
  z-index: 2400;
  width: 320px;
}

/* Scrolling lives on the inner layer, rounding and clipping on the card. Otherwise the list rides
   over the rounded corners: the scrollbar and the last item run into a square edge. */
.slash__card {
  overflow: hidden;
}

.slash__scroll {
  max-height: 320px;
  overflow-y: auto;
  /* Scrolling past the end of the list must not scroll the page beneath it. */
  overscroll-behavior: contain;
}

.slash__title {
  font-size: 13px;
}

/* The gap is set by hand: Vuetify spaces the slot only for its own VIcon/VAvatar, and here the
   icon is a plain component that sticks to the label by default. */
.slash__icon {
  color: var(--text-muted);
  margin-right: 10px;
}

/* Key labels as separate keycaps, the way the OS draws them: a solid string "Ctrl Alt 1" reads
   as text rather than as a shortcut. */
.slash__keys {
  display: inline-flex;
  align-items: center;
  gap: 3px;
  padding-left: 16px;
}
</style>
