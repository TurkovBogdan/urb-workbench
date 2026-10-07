<script setup lang="ts">
// The detail page content header: the object's name on the left, actions on it on the right.
//
// Shared by all detail pages for one reason: the actions sit in THE SAME place on every page — at
// the right edge of the first content row. A button that moves from page to page has to be found
// anew every time; a button in its place isn't searched for at all.
//
// The component doesn't render the name itself: for a research it is inline editing, for a source
// a title with an address, for a note a name with a kind. It owns the row and its right edge, and
// what stands on the left is the page's business.
import { useI18n } from 'vue-i18n'
import { IconDotsVertical, IconRefresh } from '@tabler/icons-vue'

import CopyCodeButton from '@/components/CopyCodeButton.vue'

withDefaults(defineProps<{
  /** The object's code. While it is absent (the page is loading), there is no copy button. */
  code?: string
  /** A reload in flight: the button is locked, the icon spins. */
  loading?: boolean
}>(), {
  code: '',
  loading: false,
})

const emit = defineEmits<{ refresh: [] }>()

const { t } = useI18n()
</script>

<template>
  <header class="detail-head">
    <!-- Above the name — where the object lives: the research's shelf, and for nested objects
         their place in the tree. Empty — no row at all. -->
    <div class="detail-head__above">
      <slot name="above" />
    </div>

    <div class="detail-head__name">
      <slot />
    </div>

    <!-- The page's actions sit to the right of its title — the same place and the same button as
         in `PageHeader` for lists (`variant="text"`, default size, icon 16): a detail page and a
         list differ in content, not in where to look for "Refresh".
         Left-to-right order goes from the object to the page: first "grab the code", then
         "reload". -->
    <div class="detail-head__actions">
      <slot name="actions" />
      <CopyCodeButton v-if="code" :code="code" />
      <VBtn variant="text" :disabled="loading" @click="emit('refresh')">
        <template #prepend>
          <IconRefresh :size="16" :class="{ 'icon-spin': loading }" />
        </template>
        {{ t('common.action.refresh') }}
      </VBtn>

      <!-- The rare goes last: what is done once in an object's life doesn't deserve its own
           header button, but there is no reason to hide it behind an unlabelled ellipsis either.
           The component holds the button and the list, the page supplies the items — only it
           knows their set. -->
      <VMenu v-if="$slots.more" location="bottom end" :offset="4">
        <template #activator="{ props: menu }">
          <VBtn v-bind="menu" variant="text">
            <template #prepend><IconDotsVertical :size="16" /></template>
            {{ t('common.action.more') }}
          </VBtn>
        </template>
        <VList density="compact">
          <slot name="more" />
        </VList>
      </VMenu>
    </div>
  </header>
</template>

<style scoped>
/* Two columns: the object on the left (where it lives and what it's called), actions on it on the
   right. The actions are a column, not a cell of the first row: they belong to the whole header,
   and stuck to the shelf row they would align to the small caption above the name rather than to
   the name itself. */
/* The rows are declared explicitly: without them the grid is implicit, and the actions'
   `grid-row: 1 / -1` refers to the last line of the EXPLICIT grid — i.e. the very first one — so
   they silently stick to the shelf row instead of spanning the full height. */
/* The name has a minimum width: without it the actions column (three labelled buttons) took
   everything, and in a 1233px window the name was left 144px — the title fell apart into five
   lines. Hitting that bound, the buttons wrap rather than the name: there are two or three of
   them and a second row reads fine, while a five-line name doesn't. */
.detail-head {
  display: grid;
  grid-template-columns: minmax(220px, 1fr) auto;
  grid-template-rows: auto auto;
  column-gap: 12px;
  row-gap: 2px;
  min-width: 0;
  margin-bottom: 16px;
}

.detail-head__above {
  grid-column: 1;
  min-width: 0;
  display: flex;
}

.detail-head__name {
  grid-column: 1;
  min-width: 0;
}

/* The placement is explicit: in the markup the actions come AFTER the name (first what the page
   is about, then what to do with it — that is how a screen reader reads it too), yet they stand on
   the right across the full header height. */
.detail-head__actions {
  grid-row: 1 / -1;
  grid-column: 2;
  align-self: center;
  display: flex;
  flex-wrap: wrap;
  justify-content: flex-end;
  align-items: center;
  gap: 8px;
}
</style>
