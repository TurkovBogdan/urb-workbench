<script setup lang="ts">
import { computed, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { IconArrowDown, IconArrowUp, IconPencil, IconTrash } from '@tabler/icons-vue'
import PageLayout from '@/layout/templates/PageLayout.vue'
import PageHeader from '@/layout/components/PageHeader.vue'
import ActionMenu, { type ActionMenuItem } from '@/components/ActionMenu.vue'
import CodeBlock from '@/components/CodeBlock.vue'

const { t } = useI18n()

const menu = ref<InstanceType<typeof ActionMenu>>()
const menuOpen = ref(false)
const lastAction = ref('')

function did(label: string) {
  lastAction.value = label
}

const items = computed<ActionMenuItem[]>(() => [
  { key: 'edit', icon: IconPencil, label: t('design-system.section.action-menu.edit'), hotkey: 'E', run: () => did(t('design-system.section.action-menu.edit')) },
  { key: 'delete', icon: IconTrash, label: t('design-system.section.action-menu.delete'), danger: true, hotkey: 'D', run: () => did(t('design-system.section.action-menu.delete')) },
  { key: 'up', icon: IconArrowUp, label: t('design-system.section.action-menu.up'), disabled: true, divider: true, hotkey: 'W', run: () => did(t('design-system.section.action-menu.up')) },
  { key: 'down', icon: IconArrowDown, label: t('design-system.section.action-menu.down'), hotkey: 'S', run:() => did(t('design-system.section.action-menu.down')) },
])

// `<\/script>` / `<\/template>` are escaped so they don't close this SFC's blocks.
const usageCode = `<script setup lang="ts">
import { computed, ref } from 'vue'
import { IconPencil, IconTrash } from '@tabler/icons-vue'
import ActionMenu, { type ActionMenuItem } from '@/components/ActionMenu.vue'

const menu = ref<InstanceType<typeof ActionMenu>>()
const menuOpen = ref(false)

// The key is a field of the item: the menu draws it and runs the item on it.
// Letters by meaning — E edit, D delete; C is the menu's own "Copy code"; a digit only where one was asked for
const items = computed<ActionMenuItem[]>(() => [
  { key: 'edit', icon: IconPencil, label: 'Edit', hotkey: 'E', run: edit },
  { key: 'delete', icon: IconTrash, label: 'Delete', danger: true, hotkey: 'D', run: remove },
])
<\/script>

<template>
  <!-- A right click anywhere on the row opens the same menu at the pointer -->
  <div class="row" :class="{ 'row--menu': menuOpen }" @contextmenu="menu?.openAt($event)">
    {{ entity.title }}
    <ActionMenu
      ref="menu"
      v-model:open="menuOpen"
      :items="items"
      :code="entity.code"
      label="Actions"
    />
  </div>
<\/template>`
</script>

<template>
  <PageLayout>
  <div class="ds-page">
    <PageHeader
      :title="t('design-system.page.action-menu.title')"
      :description="t('design-system.page.action-menu.description')"
      back-to="/design-system"
    />

    <!-- In context -->
    <section class="ds-section">
      <h6 class="mb-1">{{ t('design-system.section.action-menu.in_context') }}</h6>
      <p class="ds-note">{{ t('design-system.section.action-menu.in_context_note') }}</p>
      <div class="ds-card">
        <div
          class="ds-sample"
          :class="{ 'ds-sample--menu': menuOpen }"
          @contextmenu="menu?.openAt($event)"
        >
          <span class="ds-sample__title">{{ t('design-system.section.action-menu.row_title') }}</span>
          <ActionMenu
            ref="menu"
            v-model:open="menuOpen"
            :items="items"
            code="TASK@F3CE1C4436"
            :label="t('design-system.section.action-menu.actions')"
          />
        </div>
        <p class="ds-last">
          {{ t('design-system.section.action-menu.last_action') }}:
          <strong>{{ lastAction || t('design-system.section.action-menu.none') }}</strong>
        </p>
      </div>
    </section>

    <!-- Usage -->
    <section class="ds-section">
      <h6 class="mb-3">{{ t('design-system.section.action-menu.usage') }}</h6>
      <CodeBlock :code="usageCode" lang="vue" />
    </section>
  </div>
  </PageLayout>
</template>

<style scoped>
.ds-page { max-width: 860px; }
.ds-section { margin-bottom: 28px; }

.ds-note {
  margin: 0 0 12px;
  font-size: 13px;
  color: var(--text-muted);
}

.ds-card {
  background: var(--surface);
  border: 1px solid var(--border-soft);
  border-radius: var(--radius);
  overflow: hidden;
}

/* A task row in miniature: 36px, the title, and the "⋯" at the end — quiet until the row is hovered. */
.ds-sample {
  display: flex;
  align-items: center;
  gap: 8px;
  height: 36px;
  padding: 0 8px 0 16px;
  color: var(--text-muted);
}

.ds-sample:hover,
.ds-sample--menu { background: var(--surface-hi); }

.ds-sample__title {
  flex: 1;
  font-size: 13px;
  color: var(--text);
}

.ds-last {
  margin: 0;
  padding: 10px 16px;
  border-top: 1px solid var(--border-soft);
  font-size: 12px;
  color: var(--text-muted);
}
</style>
