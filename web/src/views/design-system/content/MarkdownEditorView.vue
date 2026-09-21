<script setup lang="ts">
// Витрина редактора markdown. Помимо самой зоны правки страница показывает то, ради чего
// прототип и собран: круговой проход. Источник → документ → markdown обратно, и рядом —
// вердикт, совпало ли. Структурный редактор всегда нормализует текст; вопрос не в том,
// нормализует ли он, а в том, видим ли мы это до того, как оно доедет до настоящего тела.
import { computed, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { IconCheck, IconAlertTriangle } from '@tabler/icons-vue'
import PageLayout from '@/layout/templates/PageLayout.vue'
import PageHeader from '@/layout/components/PageHeader.vue'
import MarkdownRenderer from '@/components/markdown/renderer/MarkdownRenderer.vue'
import { MarkdownEditor, UNSUPPORTED, docToMarkdown, markdownToDoc } from '@/components/markdown/editor'
// Настоящее тело заметки из стабильного ресёча, а не сочинённый пример: в нём таблицы, фенсы,
// коды сущностей в бэктиках и длинные абзацы с мягкими переносами — то есть ровно тот материал,
// на котором мост обязан работать. Подключено как файл, потому что бэктиков внутри 344 штуки и
// в шаблонной строке их пришлось бы экранировать.
import SAMPLE from './markdown-editor-sample.md?raw'

const { t } = useI18n()

const source = ref(SAMPLE)
const body = ref(SAMPLE)

// Отдельный маленький документ под таблицу. В большом образце таблицы тоже есть — и именно они
// гоняются круговым проходом ниже, — но сесть в ячейку и потрогать колонки посреди тела на две
// сотни строк неудобно. Здесь всё на экране разом: выравнивание по трём колонкам, пустая
// ячейка, `|` внутри кода и код сущности в ячейке.
const TABLE_SAMPLE = `| Конструкция | Правка | Печать обратно |
| --- | :---: | ---: |
| Заголовок | да | одна строка |
| Таблица | да | шапка, разделитель, ряды |
| Картинка | нет |  |
| Экранирование | \`a \\| b\` | AREA@0123456789 |
`

const tableBody = ref(TABLE_SAMPLE)

// Простой режим: то, чем правят короткое поле — название этапа, подпись, однострочную заметку.
// Предел взят маленьким нарочно, чтобы до красного счётчика доходило за пару фраз.
const SIMPLE_SAMPLE = 'Короткое поле: **жирный** и *курсив* есть, всего остального — нет.'

const simpleBody = ref(SIMPLE_SAMPLE)
const SIMPLE_LIMIT = 120

// Правка исходника перезаряжает редактор; правка в редакторе меняет только `body`. Вердикт
// ниже считается от исходника и потому не зависит от того, что пользователь успел натыкать.
watch(source, (value) => { body.value = value })

const roundtrip = computed(() => docToMarkdown(markdownToDoc(source.value)))
const second = computed(() => docToMarkdown(markdownToDoc(roundtrip.value)))

const identical = computed(() => roundtrip.value.trimEnd() === source.value.trimEnd())
const stable = computed(() => roundtrip.value === second.value)

interface DiffRow { line: number; before: string; after: string }

// Сравнение по наибольшей общей подпоследовательности, а не по номеру строки. Разница не
// косметическая: одна склеенная строка сдвигает весь остаток документа, и позиционный диф
// показал бы двадцать шесть расхождений там, где их два. Панель, которая преувеличивает
// потери, бесполезна ровно так же, как и та, что их прячет.
function diffLines(a: string[], b: string[]): DiffRow[] {
  const n = a.length
  const m = b.length
  const common: number[][] = Array.from({ length: n + 1 }, () => new Array<number>(m + 1).fill(0))
  for (let i = n - 1; i >= 0; i -= 1) {
    for (let j = m - 1; j >= 0; j -= 1) {
      common[i][j] = a[i] === b[j] ? common[i + 1][j + 1] + 1 : Math.max(common[i + 1][j], common[i][j + 1])
    }
  }

  const rows: DiffRow[] = []
  let hunk: { at: number; before: string[]; after: string[] } | null = null
  let i = 0
  let j = 0

  const open = () => (hunk ??= { at: i, before: [], after: [] })
  const flush = (): void => {
    if (!hunk) return
    for (let k = 0; k < Math.max(hunk.before.length, hunk.after.length); k += 1) {
      rows.push({ line: hunk.at + k + 1, before: hunk.before[k] ?? '∅', after: hunk.after[k] ?? '∅' })
    }
    hunk = null
  }

  while (i < n && j < m) {
    if (a[i] === b[j]) { flush(); i += 1; j += 1 }
    else if (common[i + 1][j] >= common[i][j + 1]) { open().before.push(a[i]); i += 1 }
    else { open().after.push(b[j]); j += 1 }
  }
  while (i < n) { open().before.push(a[i]); i += 1 }
  while (j < m) { open().after.push(b[j]); j += 1 }
  flush()

  return rows
}

const diff = computed(() => diffLines(source.value.trimEnd().split('\n'), roundtrip.value.trimEnd().split('\n')))
</script>

<template>
  <PageLayout>
    <div class="ds-page">
      <PageHeader
        :title="t('design-system.page.markdown-editor.title')"
        :description="t('design-system.page.markdown-editor.description')"
        back-to="/design-system"
      />

      <!-- Зона редактирования -->
      <section class="ds-section">
        <h6 class="mb-3">{{ t('design-system.section.markdown-editor.editor') }}</h6>
        <MarkdownEditor v-model="body" />
        <p class="ds-note mt-2">{{ t('design-system.section.markdown-editor.editorHint') }}</p>
      </section>

      <!-- Простой режим: состав возможностей как контракт поля -->
      <section class="ds-section">
        <h6 class="mb-3">{{ t('design-system.section.markdown-editor.simple') }}</h6>
        <MarkdownEditor
          v-model="simpleBody"
          mode="simple"
          min-height="120px"
          :max-length="SIMPLE_LIMIT"
        />
        <p class="ds-note mt-2">{{ t('design-system.section.markdown-editor.simpleHint') }}</p>

        <div class="pane-grid mt-4">
          <div class="pane">
            <span class="ds-tag mb-2">{{ t('design-system.section.markdown-editor.emitted') }}</span>
            <pre class="code-box code-box--short">{{ simpleBody }}</pre>
          </div>
          <div class="pane">
            <span class="ds-tag mb-2">{{ t('design-system.section.markdown-editor.rendered') }}</span>
            <div class="preview-box">
              <MarkdownRenderer :text="simpleBody" />
            </div>
          </div>
        </div>
      </section>

      <!-- Таблица: единственный блок, который не ложится в одну строку markdown -->
      <section class="ds-section">
        <h6 class="mb-3">{{ t('design-system.section.markdown-editor.table') }}</h6>
        <MarkdownEditor v-model="tableBody" min-height="220px" />
        <p class="ds-note mt-2">{{ t('design-system.section.markdown-editor.tableHint') }}</p>

        <div class="pane-grid mt-4">
          <div class="pane">
            <span class="ds-tag mb-2">{{ t('design-system.section.markdown-editor.emitted') }}</span>
            <pre class="code-box code-box--short">{{ tableBody }}</pre>
          </div>
          <div class="pane">
            <span class="ds-tag mb-2">{{ t('design-system.section.markdown-editor.rendered') }}</span>
            <div class="preview-box">
              <MarkdownRenderer :text="tableBody" />
            </div>
          </div>
        </div>
      </section>

      <!-- Круговой проход -->
      <section class="ds-section">
        <h6 class="mb-3">{{ t('design-system.section.markdown-editor.roundtrip') }}</h6>

        <div class="verdicts">
          <div class="verdict" :class="identical ? 'verdict--ok' : 'verdict--warn'">
            <component :is="identical ? IconCheck : IconAlertTriangle" :size="16" />
            <span>{{ t(identical
              ? 'design-system.section.markdown-editor.identicalYes'
              : 'design-system.section.markdown-editor.identicalNo') }}</span>
          </div>
          <div class="verdict" :class="stable ? 'verdict--ok' : 'verdict--warn'">
            <component :is="stable ? IconCheck : IconAlertTriangle" :size="16" />
            <span>{{ t(stable
              ? 'design-system.section.markdown-editor.stableYes'
              : 'design-system.section.markdown-editor.stableNo') }}</span>
          </div>
        </div>

        <div class="pane-grid mt-4">
          <div class="pane">
            <span class="ds-tag mb-2">{{ t('design-system.section.markdown-editor.source') }}</span>
            <VTextarea
              v-model="source"
              variant="outlined"
              density="compact"
              rows="18"
              hide-details
              style="font-family: var(--font-mono); font-size: 12px"
            />
          </div>
          <div class="pane">
            <span class="ds-tag mb-2">{{ t('design-system.section.markdown-editor.emitted') }}</span>
            <pre class="code-box">{{ roundtrip }}</pre>
          </div>
        </div>

        <div v-if="diff.length" class="mt-4">
          <span class="ds-tag mb-2">{{ t('design-system.section.markdown-editor.diff') }}</span>
          <div class="ds-card">
            <div v-for="row in diff" :key="row.line" class="diff-row">
              <span class="diff-line">{{ row.line }}</span>
              <span class="diff-before">{{ row.before }}</span>
              <span class="diff-after">{{ row.after }}</span>
            </div>
          </div>
        </div>
      </section>

      <!-- Живой вывод -->
      <section class="ds-section">
        <h6 class="mb-3">{{ t('design-system.section.markdown-editor.output') }}</h6>
        <div class="pane-grid">
          <div class="pane">
            <span class="ds-tag mb-2">{{ t('design-system.section.markdown-editor.emitted') }}</span>
            <pre class="code-box">{{ body }}</pre>
          </div>
          <div class="pane">
            <span class="ds-tag mb-2">{{ t('design-system.section.markdown-editor.rendered') }}</span>
            <div class="preview-box">
              <MarkdownRenderer :text="body" />
            </div>
          </div>
        </div>
      </section>

      <!-- Охват -->
      <section class="ds-section">
        <h6 class="mb-3">{{ t('design-system.section.markdown-editor.coverage') }}</h6>
        <div class="ds-card pa-4">
          <p class="ds-note mb-2">{{ t('design-system.section.markdown-editor.unsupported') }}</p>
          <div class="chips">
            <VChip v-for="item in UNSUPPORTED" :key="item" size="small" variant="tonal" color="warning">{{ item }}</VChip>
          </div>
        </div>
      </section>
    </div>
  </PageLayout>
</template>

<style scoped>
.ds-page {
  max-width: 1100px;
}

.ds-section {
  margin-bottom: 32px;
}

.ds-card {
  background: var(--surface);
  border: 1px solid var(--border-soft);
  border-radius: var(--radius);
  overflow: hidden;
}

.ds-tag {
  font-family: var(--font-mono);
  font-size: 11px;
  color: var(--text-faint);
  display: block;
}

.ds-note {
  font-size: 12px;
  color: var(--text-muted);
}

.pane-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 16px;
  align-items: start;
}

.pane {
  display: flex;
  flex-direction: column;
  gap: 6px;
  min-width: 0;
}

.code-box {
  font-family: var(--font-mono);
  font-size: 12px;
  line-height: 1.55;
  white-space: pre-wrap;
  word-break: break-word;
  margin: 0;
  padding: 12px 14px;
  min-height: 320px;
  background: var(--surface);
  border: 1px solid var(--border-soft);
  border-radius: var(--radius);
  color: var(--text-muted);
}

/* У маленького примера высота по содержимому: пустая панель на треть экрана под таблицей из
   пяти строк читалась бы как «тут что-то не загрузилось». */
.code-box--short {
  min-height: 0;
}

.preview-box {
  background: var(--surface);
  border: 1px solid var(--border-soft);
  border-radius: var(--radius);
  padding: 20px 24px;
}

/* ── Вердикты ─────────────────────────────────────────────── */

.verdicts {
  display: flex;
  gap: 12px;
  flex-wrap: wrap;
}

.verdict {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  font-size: 12px;
  padding: 6px 12px;
  border-radius: var(--radius);
  border: 1px solid var(--border-soft);
}

.verdict--ok {
  color: rgb(var(--v-theme-success));
  border-color: color-mix(in srgb, rgb(var(--v-theme-success)) 35%, transparent);
  background: color-mix(in srgb, rgb(var(--v-theme-success)) 8%, transparent);
}

.verdict--warn {
  color: rgb(var(--v-theme-warning));
  border-color: color-mix(in srgb, rgb(var(--v-theme-warning)) 35%, transparent);
  background: color-mix(in srgb, rgb(var(--v-theme-warning)) 8%, transparent);
}

/* ── Диф ──────────────────────────────────────────────────── */

.diff-row {
  display: grid;
  grid-template-columns: 44px 1fr 1fr;
  gap: 12px;
  padding: 6px 14px;
  font-family: var(--font-mono);
  font-size: 11px;
  border-bottom: 1px solid var(--border-soft);
}

.diff-row:last-child {
  border-bottom: none;
}

.diff-line {
  color: var(--text-faint);
}

.diff-before {
  color: rgb(var(--v-theme-error));
  word-break: break-word;
}

.diff-after {
  color: rgb(var(--v-theme-success));
  word-break: break-word;
}

.chips {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}
</style>
