<script setup lang="ts">
import { ref } from 'vue'
import { useI18n } from 'vue-i18n'

import PageLayout from '@/layout/templates/PageLayout.vue'
import PageHeader from '@/layout/components/PageHeader.vue'
import CodeBlock from '@/components/CodeBlock.vue'
import GroupSelect from '@/features/research/components/GroupSelect.vue'
import { useGroupCatalogStore } from '@/features/research/stores/group-catalog.store'

const { t } = useI18n()

// Витрина работает на живом справочнике — здесь же видно, что компонент грузит полки сам.
const catalog = useGroupCatalogStore()

const filterValue = ref<string | null>(null)
const formValue = ref<string | null>(null)
const excludeValue = ref<string | null>(null)

const usageSnippet = `<script setup lang="ts">
import GroupSelect from '@/features/research/components/GroupSelect.vue'
import { ref } from 'vue'

const groupCode = ref<string | null>(null)
<\/script>

<template>
  <!-- Filter: "All groups" clears the narrowing, "No group" leaves the ungrouped -->
  <GroupSelect v-model="groupCode" with-all with-ungrouped />

  <!-- Form: only real groups -->
  <GroupSelect v-model="groupCode" :label="'Group'" autofocus />

  <!-- Reassigning on delete: the source group can't be picked -->
  <GroupSelect v-model="moveTo" :exclude="group.code" />
<\/template>`
</script>

<template>
  <PageLayout>
    <div class="ds-page">
      <PageHeader
        :title="t('design-system.page.group-select.title')"
        :description="t('design-system.page.group-select.description')"
        back-to="/design-system"
      />

      <section class="ds-section">
        <h6 class="mb-3">{{ t('design-system.section.group-select.variants') }}</h6>
        <div class="ds-card">

          <div class="ds-row ds-row--center">
            <span class="ds-tag">with-all · with-ungrouped</span>
            <div class="ds-controls">
              <GroupSelect v-model="filterValue" with-all with-ungrouped />
            </div>
            <span class="ds-spec">list filter</span>
          </div>

          <div class="ds-row ds-row--center">
            <span class="ds-tag">default</span>
            <div class="ds-controls">
              <GroupSelect v-model="formValue" />
            </div>
            <span class="ds-spec">group-binding dialog</span>
          </div>

          <div class="ds-row ds-row--center">
            <span class="ds-tag">exclude</span>
            <div class="ds-controls">
              <GroupSelect v-model="excludeValue" :exclude="catalog.items[0]?.code" />
            </div>
            <span class="ds-spec">
              {{ catalog.items[0]?.title ? `without «${catalog.items[0].title}»` : 'without one group' }}
            </span>
          </div>

        </div>

        <p class="ds-note">
          The value is a group code (<code>GROUP@…</code>), <code>null</code> is the "All groups" item,
          <code>GROUP@</code> is "No group" (the backend reads an empty code as "ungrouped only").
          The pseudo-items appear only on request: the form doesn't need them, the filter needs both.
        </p>

        <p class="ds-note">
          The component pulls the set of groups from the catalog
          (<code>group-catalog.store</code>) and loads it itself if nobody has yet —
          the call site doesn't need to know about that or hold a loading flag. The catalog
          is also filled from the groups page: the list that lands there is reused without a second request.
          Right now it holds {{ catalog.items.length }} groups, loaded — {{ catalog.loaded ? 'yes' : 'no' }}.
        </p>

        <CodeBlock :code="usageSnippet" lang="vue" variant="icon" class="mt-3" />
      </section>
    </div>
  </PageLayout>
</template>

<style scoped>
.ds-page { max-width: 860px; }
.ds-section { margin-bottom: 28px; }

.ds-card {
  background: var(--surface);
  border: 1px solid var(--border-soft);
  border-radius: var(--radius);
  overflow: hidden;
}

.ds-row {
  display: grid;
  grid-template-columns: 160px 1fr 200px;
  align-items: start;
  gap: 16px;
  padding: 12px 16px;
  border-bottom: 1px solid var(--border-soft);
}

.ds-row:last-child { border-bottom: none; }
.ds-row--center { align-items: center; }

.ds-tag {
  font-family: var(--font-mono);
  font-size: 11px;
  color: var(--text-faint);
}

.ds-spec {
  font-family: var(--font-mono);
  font-size: 10px;
  color: var(--text-faint);
  text-align: right;
}

.ds-controls :deep(.v-select) {
  min-width: 220px;
  max-width: 280px;
}

.ds-note {
  margin-top: 14px;
  font-size: 12px;
  line-height: 1.5;
  color: var(--text-muted);
}

.ds-note code {
  font-family: var(--font-mono);
  font-size: 11px;
}
</style>
