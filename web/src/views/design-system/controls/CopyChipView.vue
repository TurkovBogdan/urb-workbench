<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import PageLayout from '@/layout/templates/PageLayout.vue'
import PageHeader from '@/layout/components/PageHeader.vue'
import CopyChip from '@/components/CopyChip.vue'
import CodeBlock from '@/components/CodeBlock.vue'

const { t } = useI18n()

const LONG_PATH = '/mnt/store-dev/agents/mcp/urb-workbench/runtime/prod/storage/private/exports/2026-09-24/tasks.json'

// `<\/script>` / `<\/template>` экранированы, чтобы не закрыть блоки этого SFC.
const usageCode = `<script setup lang="ts">
import CopyChip from '@/components/CopyChip.vue'
<\/script>

<template>
  <!-- Entity code: the value is the label -->
  <CopyChip :text="task.code" hint="Copy code" />

  <!-- Show it short, copy it whole -->
  <CopyChip :text="token" label="wmVd…A5OF0" />
<\/template>

<style scoped>
/* Idle color sets where it's used */
.muted-row { --copy-chip-color: var(--text-faint); }
<\/style>`
</script>

<template>
  <PageLayout>
  <div class="ds-page">
    <PageHeader
      :title="t('design-system.page.copy-chip.title')"
      :description="t('design-system.page.copy-chip.description')"
      back-to="/design-system"
    />

    <!-- In context -->
    <section class="ds-section">
      <h6 class="mb-1">{{ t('design-system.section.copy-chip.in_context') }}</h6>
      <p class="ds-note">{{ t('design-system.section.copy-chip.in_context_note') }}</p>
      <div class="ds-card ds-sample">
        <p class="ds-sample__title">{{ t('design-system.section.copy-chip.title_sample') }}</p>
        <CopyChip text="TASK@e9891c96d0" :hint="t('common.action.copy_code')" class="ds-sample__code" />
      </div>
    </section>

    <!-- Variants -->
    <section class="ds-section">
      <h6 class="mb-3">{{ t('design-system.section.copy-chip.variants') }}</h6>
      <div class="ds-card">
        <div class="ds-row">
          <span class="ds-tag">text</span>
          <div class="ds-controls">
            <CopyChip text="GROUP@26be3ee9c2" />
            <span class="ds-caption">{{ t('design-system.section.copy-chip.code') }}</span>
          </div>
          <span class="ds-spec">:text</span>
        </div>
        <div class="ds-row">
          <span class="ds-tag">label</span>
          <div class="ds-controls">
            <CopyChip text="wmVdvA4AkjdySRX4irvwkIN4lX5n3EXB15NPi9A5OF0" label="wmVd…A5OF0" />
            <span class="ds-caption">{{ t('design-system.section.copy-chip.label') }}</span>
          </div>
          <span class="ds-spec">:label</span>
        </div>
        <div class="ds-row">
          <span class="ds-tag">long</span>
          <div class="ds-controls">
            <CopyChip :text="LONG_PATH" />
            <span class="ds-caption">{{ t('design-system.section.copy-chip.long') }}</span>
          </div>
          <span class="ds-spec">max-width: 100%</span>
        </div>
        <div class="ds-row">
          <span class="ds-tag">hint</span>
          <div class="ds-controls">
            <CopyChip text="TASK@1eb0940a10" :hint="t('common.action.copy_code')" />
            <span class="ds-caption">{{ t('design-system.section.copy-chip.hint') }}</span>
          </div>
          <span class="ds-spec">:hint</span>
        </div>
      </div>
    </section>

    <!-- Usage -->
    <section class="ds-section">
      <h6 class="mb-3">{{ t('design-system.section.copy-chip.usage') }}</h6>
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

/* Образец повторяет шапку страницы задачи: название, под ним код с тем же отступом плашки. */
.ds-sample { padding: 14px 16px; }

.ds-sample__title {
  margin: 0 0 2px;
  font-size: 15px;
  font-weight: 600;
  color: var(--text);
}

.ds-sample__code { margin-inline-start: -5px; }

.ds-row {
  display: grid;
  grid-template-columns: 100px 1fr 140px;
  align-items: center;
  gap: 16px;
  padding: 12px 16px;
  border-bottom: 1px solid var(--border-soft);
  &:last-child { border-bottom: none; }
}

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

/* Колонка плашки фиксированной ширины: у плашек разная длина, а подписи должны стоять в линию. */
.ds-controls {
  display: grid;
  grid-template-columns: 220px 1fr;
  justify-items: start;
  align-items: center;
  gap: 12px;
  min-width: 0;
}

.ds-controls > :first-child { max-width: 100%; }

.ds-caption {
  font-size: 12px;
  color: var(--text-muted);
}
</style>
