<script setup lang="ts">
import { ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { IconListCheck, IconSubtask } from '@tabler/icons-vue'
import PageLayout from '@/layout/templates/PageLayout.vue'
import PageHeader from '@/layout/components/PageHeader.vue'
import CounterButton from '@/components/CounterButton.vue'
import CodeBlock from '@/components/CodeBlock.vue'

const { t } = useI18n()

const groupFolded = ref(false)
const taskFolded = ref(true)

const label = (folded: boolean) =>
  t(folded ? 'design-system.section.counter-button.expand' : 'design-system.section.counter-button.collapse')

// `<\/script>` / `<\/template>` экранированы, чтобы не закрыть блоки этого SFC.
const usageCode = `<script setup lang="ts">
import { ref } from 'vue'
import { IconSubtask } from '@tabler/icons-vue'
import CounterButton from '@/components/CounterButton.vue'

const folded = ref(false)
<\/script>

<template>
  <!-- Click and Enter don't bubble: the button won't open the row around it -->
  <CounterButton
    :icon="IconSubtask"
    :count="19"
    :folded="folded"
    :label="folded ? 'Expand subtasks' : 'Collapse subtasks'"
    @toggle="folded = !folded"
  />
<\/template>

<style scoped>
/* Reveal the button while the cursor is over the row */
.row:hover { --counter-button-color: var(--text-muted); }
<\/style>`
</script>

<template>
  <PageLayout>
  <div class="ds-page">
    <PageHeader
      :title="t('design-system.page.counter-button.title')"
      :description="t('design-system.page.counter-button.description')"
      back-to="/design-system"
    />

    <!-- In context -->
    <section class="ds-section">
      <h6 class="mb-1">{{ t('design-system.section.counter-button.in_context') }}</h6>
      <p class="ds-note">{{ t('design-system.section.counter-button.in_context_note') }}</p>
      <div class="ds-card">
        <div class="ds-sample ds-sample--group">
          <span>{{ t('design-system.section.counter-button.group_title') }}</span>
          <CounterButton
            class="ds-sample__button ds-sample__button--group"
            :icon="IconListCheck"
            :count="12"
            :folded="groupFolded"
            :label="label(groupFolded)"
            @toggle="groupFolded = !groupFolded"
          />
        </div>
        <div class="ds-sample ds-sample--task">
          <span>{{ t('design-system.section.counter-button.task_title') }}</span>
          <CounterButton
            class="ds-sample__button ds-sample__button--task"
            :icon="IconSubtask"
            :count="19"
            :folded="taskFolded"
            :label="label(taskFolded)"
            @toggle="taskFolded = !taskFolded"
          />
        </div>
      </div>
    </section>

    <!-- States -->
    <section class="ds-section">
      <h6 class="mb-3">{{ t('design-system.section.counter-button.states') }}</h6>
      <div class="ds-card">
        <div class="ds-row">
          <span class="ds-tag">expanded</span>
          <div class="ds-controls">
            <CounterButton :icon="IconSubtask" :count="3" :folded="false" :label="label(false)" />
            <span class="ds-caption">{{ t('design-system.section.counter-button.expanded') }}</span>
          </div>
          <span class="ds-spec">:folded="false"</span>
        </div>
        <div class="ds-row">
          <span class="ds-tag">folded</span>
          <div class="ds-controls">
            <CounterButton :icon="IconSubtask" :count="3" :folded="true" :label="label(true)" />
            <span class="ds-caption">{{ t('design-system.section.counter-button.folded') }}</span>
          </div>
          <span class="ds-spec">:folded="true"</span>
        </div>
        <div class="ds-row">
          <span class="ds-tag">zero</span>
          <div class="ds-controls">
            <CounterButton :icon="IconListCheck" :count="0" :folded="true" :label="label(true)" />
            <span class="ds-caption">{{ t('design-system.section.counter-button.zero') }}</span>
          </div>
          <span class="ds-spec">:count="0"</span>
        </div>
        <div class="ds-row">
          <span class="ds-tag">no count</span>
          <div class="ds-controls">
            <CounterButton :icon="IconSubtask" :folded="false" :label="label(false)" />
            <span class="ds-caption">{{ t('design-system.section.counter-button.no_count') }}</span>
          </div>
          <span class="ds-spec">count not passed</span>
        </div>
      </div>
    </section>

    <!-- Resting tint -->
    <section class="ds-section">
      <h6 class="mb-1">{{ t('design-system.section.counter-button.tint') }}</h6>
      <p class="ds-note">{{ t('design-system.section.counter-button.tint_note') }}</p>
      <div class="ds-card">
        <div class="ds-row">
          <span class="ds-tag">default</span>
          <div class="ds-controls">
            <CounterButton :icon="IconSubtask" :count="7" :folded="false" :label="label(false)" />
            <span class="ds-caption">{{ t('design-system.section.counter-button.tint_default') }}</span>
          </div>
          <span class="ds-spec">var(--text-faint)</span>
        </div>
        <div class="ds-row ds-row--muted">
          <span class="ds-tag">muted</span>
          <div class="ds-controls">
            <CounterButton :icon="IconSubtask" :count="7" :folded="false" :label="label(false)" />
            <span class="ds-caption">{{ t('design-system.section.counter-button.tint_muted') }}</span>
          </div>
          <span class="ds-spec">--counter-button-color</span>
        </div>
      </div>
    </section>

    <!-- Usage -->
    <section class="ds-section">
      <h6 class="mb-3">{{ t('design-system.section.counter-button.usage') }}</h6>
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

/* Образцы повторяют строку имени группы и строку задачи из списка — кегль, вес и отступ кнопки
   от текста те же, что там, иначе витрина показывала бы не ту кнопку, что стоит на экране. */
.ds-sample {
  display: flex;
  align-items: center;
  gap: 8px;
  height: 44px;
  padding: 0 16px;
  font-size: 13px;
  color: var(--text);
  border-bottom: 1px solid var(--border-soft);
  &:last-child { border-bottom: none; }
}

.ds-sample--group { font-weight: 600; }
.ds-sample--task { gap: 2px; height: 36px; }

.ds-sample__button--group { margin-inline-start: -4px; }
.ds-sample__button--task { margin-inline: 2px -4px; }

.ds-sample:hover { --counter-button-color: var(--text-muted); }

.ds-row {
  display: grid;
  grid-template-columns: 100px 1fr 200px;
  align-items: center;
  gap: 16px;
  padding: 12px 16px;
  border-bottom: 1px solid var(--border-soft);
  &:last-child { border-bottom: none; }
}

.ds-row--muted { --counter-button-color: var(--text-muted); }

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

/* Колонка кнопки фиксированной ширины: без числа кнопка уже, и подписи строк разъехались бы. */
.ds-controls {
  display: grid;
  grid-template-columns: 56px 1fr;
  justify-items: start;
  align-items: center;
  gap: 12px;
}

.ds-caption {
  font-size: 12px;
  color: var(--text-muted);
}
</style>
