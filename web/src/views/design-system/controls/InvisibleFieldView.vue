<script setup lang="ts">
// The invisible field: a value edited right where it is read. The demo puts it in the two places
// it is made for — a page title and a line of body text — next to the same text as a plain heading,
// so the eye can check that nothing gives the field away until the caret is in it.
import { ref } from 'vue'
import { useI18n } from 'vue-i18n'

import PageLayout from '@/layout/templates/PageLayout.vue'
import PageHeader from '@/layout/components/PageHeader.vue'
import CodeBlock from '@/components/CodeBlock.vue'
import InvisibleField from '@/components/InvisibleField.vue'

const { t } = useI18n()

const heading = ref(t('design-system.section.invisible-field.sample_heading'))
const line = ref(t('design-system.section.invisible-field.sample_line'))
const empty = ref('')

const usageSnippet = `<InvisibleField
  :model-value="draft.title"
  :placeholder="t('tasks.task.detail.name')"
  :aria-label="t('tasks.task.detail.name')"
  :maxlength="TASK_TITLE_MAX"
  class="task-page__title"
  @update:model-value="(value) => { draft.title = value; schedule() }"
  @blur="commit"
/>

/* The size of the text is the place's, not the field's. */
.task-page__title :deep(.v-field__input) {
  font-size: 22px;
  font-weight: 700;
  line-height: 28px;
}`
</script>

<template>
  <PageLayout>
    <div class="ds-page">
      <PageHeader
        :title="t('design-system.page.invisible-field.title')"
        :description="t('design-system.page.invisible-field.description')"
        back-to="/design-system"
      />

      <section class="ds-section">
        <h6 class="mb-3">{{ t('design-system.section.invisible-field.basic') }}</h6>
        <div class="ds-card">
          <div class="ds-row">
            <span class="ds-tag">heading</span>
            <div class="ds-controls">
              <InvisibleField
                v-model="heading"
                :aria-label="t('design-system.section.invisible-field.heading')"
                class="ds-heading"
              />
              <p class="ds-value">{{ heading }}</p>
            </div>
            <span class="ds-spec">v-model, class</span>
          </div>

          <div class="ds-row">
            <span class="ds-tag">text</span>
            <div class="ds-controls">
              <InvisibleField
                v-model="line"
                :aria-label="t('design-system.section.invisible-field.line')"
                class="ds-line"
              />
            </div>
            <span class="ds-spec">class</span>
          </div>

          <div class="ds-row">
            <span class="ds-tag">empty</span>
            <div class="ds-controls">
              <InvisibleField
                v-model="empty"
                :placeholder="t('design-system.section.invisible-field.placeholder')"
                :error="!empty.trim()"
                class="ds-heading"
              />
            </div>
            <span class="ds-spec">placeholder, :error</span>
          </div>

          <div class="ds-row">
            <span class="ds-tag">disabled</span>
            <div class="ds-controls">
              <InvisibleField
                :model-value="t('design-system.section.invisible-field.sample_heading')"
                disabled
                class="ds-heading"
              />
            </div>
            <span class="ds-spec">disabled</span>
          </div>
        </div>
      </section>

      <section class="ds-section">
        <h6 class="mb-3">{{ t('design-system.section.invisible-field.parts') }}</h6>
        <div class="ds-card">
          <div class="ds-row">
            <span class="ds-tag">chrome</span>
            <p class="ds-part">{{ t('design-system.section.invisible-field.part.chrome') }}</p>
            <span class="ds-spec">variant="plain"</span>
          </div>
          <div class="ds-row">
            <span class="ds-tag">edge</span>
            <p class="ds-part">{{ t('design-system.section.invisible-field.part.edge') }}</p>
            <span class="ds-spec">padding-inline: 0</span>
          </div>
          <div class="ds-row">
            <span class="ds-tag">size</span>
            <p class="ds-part">{{ t('design-system.section.invisible-field.part.size') }}</p>
            <span class="ds-spec">:deep(.v-field__input)</span>
          </div>
          <div class="ds-row">
            <span class="ds-tag">where</span>
            <p class="ds-part">{{ t('design-system.section.invisible-field.part.where') }}</p>
            <span class="ds-spec">TaskView, TaskNoteView</span>
          </div>
        </div>
      </section>

      <section class="ds-section">
        <h6 class="mb-3">{{ t('design-system.section.invisible-field.usage') }}</h6>
        <CodeBlock :code="usageSnippet" lang="vue" />
      </section>
    </div>
  </PageLayout>
</template>

<style scoped>
.ds-page { max-width: 900px; }
.ds-section { margin-bottom: 28px; }

.ds-card {
  background: var(--surface);
  border: 1px solid var(--border-soft);
  border-radius: var(--radius);
  overflow: hidden;
}

.ds-row {
  display: grid;
  grid-template-columns: 100px 1fr 200px;
  align-items: start;
  gap: 16px;
  padding: 12px 16px;
  border-bottom: 1px solid var(--border-soft);
}
.ds-row:last-child { border-bottom: none; }

.ds-tag {
  font-family: var(--font-mono);
  font-size: 11px;
  color: var(--text-faint);
  padding-top: 10px;
}

.ds-spec {
  font-family: var(--font-mono);
  font-size: 10px;
  color: var(--text-faint);
  text-align: right;
  padding-top: 10px;
}

.ds-controls { min-width: 0; }

.ds-value {
  margin: 8px 0 0;
  font-family: var(--font-mono);
  font-size: 11px;
  color: var(--text-muted);
}

.ds-part {
  margin: 0;
  font-size: 13px;
  color: var(--text-muted);
  line-height: 1.5;
}

/* The page title's metrics, as on the task page. */
.ds-heading :deep(.v-field__input) {
  min-height: 28px;
  padding-block: 4px;
  font-size: 22px;
  font-weight: 700;
  line-height: 28px;
}

.ds-line :deep(.v-field__input) {
  font-size: 13px;
}
</style>
