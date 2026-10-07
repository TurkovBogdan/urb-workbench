<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref } from 'vue'
import { IconArrowLeft } from '@tabler/icons-vue'
import { useRouter, type RouteLocationRaw } from 'vue-router'
import { useNavigationHistory } from '@/composables/useNavigationHistory'
import SectionHeader from '@/components/SectionHeader.vue'

// Page header = a "back" button + a first-level heading. The heading itself is rendered by
// SectionHeader: the anatomy (title, description, right side, placeholders) is the same for a page
// and a section inside it, and only the way back belongs to the page.
const props = defineProps<{
  title: string
  description?: string
  backTo?: RouteLocationRaw
  loading?: boolean
}>()

const router = useRouter()
const { goBack } = useNavigationHistory()

// Alignment is decided by measurement, not markup: a heading may have an overline, a description,
// or just be long — these cases can't be told apart by eye, yet the rule is one. While the text
// fits within the neighbour's height, both boxes center on each other; once the text outgrows the
// neighbour (a second line, an overline, a description), it reads top-down, and the neighbour
// aligns to its top edge.
//
// The neighbour is the "back" button, and without it the title line itself is the measure: on a
// page with no way back the question is no longer about the button but about the actions on the
// right, and "the text outgrew its name" means exactly "there is something under the name".
//
// The text half is measured, not the whole heading: the right side with actions alone would make
// any heading "outgrown". The classes are someone else's (`SectionHeader`), but the two are one
// anatomy anyway — the header is built on top of it.
const root = ref<HTMLElement | null>(null)
const textFitsItsNeighbour = ref(true)

let sizeWatcher: ResizeObserver | undefined

function measuredParts(): { text: HTMLElement; reference: HTMLElement } | null {
  const text = root.value?.querySelector('.section-header__text')
  const reference =
    root.value?.querySelector('.page-header__before') ??
    root.value?.querySelector('.section-header__title')
  if (!(text instanceof HTMLElement) || !(reference instanceof HTMLElement)) return null
  return { text, reference }
}

function syncAlignment(): void {
  const parts = measuredParts()
  if (!parts) return
  textFitsItsNeighbour.value = parts.text.offsetHeight <= parts.reference.offsetHeight
}

onMounted(() => {
  const parts = measuredParts()
  if (!parts) return

  sizeWatcher = new ResizeObserver(syncAlignment)
  sizeWatcher.observe(parts.text)
  sizeWatcher.observe(parts.reference)
  syncAlignment()
})

onBeforeUnmount(() => sizeWatcher?.disconnect())
</script>

<template>
  <div ref="root" class="page-header" :class="{ 'page-header--single-line': textFitsItsNeighbour }">
    <div v-if="$slots.before || backTo" class="page-header__before">
      <slot name="before">
        <VBtn
          :icon="IconArrowLeft"
          variant="tonal"
          density="comfortable"
          rounded="0"
          class="page-header__back"
          @click="goBack(router, props.backTo!)"
        />
      </slot>
    </div>

    <SectionHeader :level="1" :title="title" :description="description" :loading="loading">
      <!-- The title is handed over entirely to its own component (inline title editing): pass
           the SectionHeader slot through as is — such a component sets its own metrics. -->
      <template v-if="$slots.title" #title>
        <slot name="title" />
      </template>
      <template v-if="$slots.description" #description>
        <slot name="description" />
      </template>
      <template v-if="$slots.actions" #right>
        <slot name="actions" />
      </template>
    </SectionHeader>
  </div>
</template>

<style scoped>
/* TOP-aligned by default: a heading with an overline, a description or just a wrap reads top-down,
   and the button belongs to its first line, not the middle of a paragraph. The script computes the
   exception: while the text fits the button's height they center on each other — a lone line
   pinned to the top would hang above the button's middle. */
.page-header {
  display: flex;
  align-items: flex-start;
  gap: 16px;
  margin-bottom: 16px;
  flex-wrap: nowrap;
}

.page-header--single-line {
  align-items: center;
}

.page-header__before {
  display: flex;
  flex-shrink: 0;
}

/* The box is set here, not via the `size` prop: for an icon button Vuetify computes the side as
   `--v-btn-height + 12px`, and `density` only changes the height — both knobs give either a
   rectangle or a larger size than needed. An unlayered rule overrides `@layer vuetify-components`
   (docs/frontend/vuetify-css-patterns). */
.page-header__back {
  width: 32px;
  min-width: 32px;
  height: 32px;
}

/* The heading is pulled toward the button: the button has its own inner padding box. */
.page-header__before + * {
  margin-left: -8px;
}

@media (max-width: 959px) {
  .page-header {
    flex-wrap: wrap;
  }
}
</style>
