<script setup lang="ts">
// Markdown editor showcase. Besides the editing zone itself, the page shows what the prototype
// was built for: the round trip. Source → document → markdown back, with a verdict beside it on
// whether they match. A structural editor always normalizes text; the question isn't whether it
// normalizes, but whether we see it before it reaches a real body.
import { computed, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { IconCheck, IconAlertTriangle } from '@tabler/icons-vue'
import PageLayout from '@/layout/templates/PageLayout.vue'
import PageHeader from '@/layout/components/PageHeader.vue'
import MarkdownRenderer from '@/components/markdown/renderer/MarkdownRenderer.vue'
import { MarkdownEditor, UNSUPPORTED, docToMarkdown, markdownToDoc } from '@/components/markdown/editor'
import type { Feature } from '@/components/markdown/editor/modes'
// A real note body from the stable research, not a made-up example: it has tables, fences,
// entity codes in backticks and long paragraphs with soft wraps — exactly the material the bridge
// must work on. Imported as a file because it contains 344 backticks, which would all need
// escaping in a template string.
import SAMPLE from './markdown-editor-sample.md?raw'

const { t } = useI18n()

const source = ref(SAMPLE)
const body = ref(SAMPLE)

// A separate small document for the table. The big sample has tables too — and those are exactly
// what the round trip below exercises — but stepping into a cell and poking at columns in the
// middle of a two-hundred-line body is awkward. Here everything is on screen at once: alignment
// across three columns, an empty cell, a `|` inside code and an entity code in a cell.
const TABLE_SAMPLE = `| Construct | Editable | Printed back |
| --- | :---: | ---: |
| Heading | yes | single line |
| Table | yes | header, separator, rows |
| Image | no |  |
| Escaping | \`a \\| b\` | AREA@0123456789 |
`

const tableBody = ref(TABLE_SAMPLE)

// A diagram block, and the same fence in a field that has code blocks but no diagrams: there it
// stays the fence it was, shown as code.
const DIAGRAM_SAMPLE = `Editor and renderer share the parser:

\`\`\`mermaid
flowchart LR
  body[(Body)] --> parse[markdownToDoc] --> doc[Document] --> print[docToMarkdown] --> body
\`\`\``

const diagramBody = ref(DIAGRAM_SAMPLE)
const codeOnlyBody = ref(DIAGRAM_SAMPLE)
const CODE_ONLY: readonly Feature[] = ['codeBlock', 'bold', 'italic', 'code', 'slash']

// Simple mode: what a short field is edited with — a stage title, a caption, a one-line note.
// The limit is deliberately small so the counter turns red within a couple of phrases.
const SIMPLE_SAMPLE = 'Short field: **bold** and *italic* are supported, nothing else is.'

const simpleBody = ref(SIMPLE_SAMPLE)
const SIMPLE_LIMIT = 120

// Editing the source reloads the editor; editing in the editor changes only `body`. The verdict
// below is computed from the source and so doesn't depend on whatever the user has clicked in.
watch(source, (value) => { body.value = value })

const roundtrip = computed(() => docToMarkdown(markdownToDoc(source.value)))
const second = computed(() => docToMarkdown(markdownToDoc(roundtrip.value)))

const identical = computed(() => roundtrip.value.trimEnd() === source.value.trimEnd())
const stable = computed(() => roundtrip.value === second.value)

interface DiffRow { line: number; before: string; after: string }

// Comparison by longest common subsequence, not by line number. The difference isn't cosmetic:
// one merged line shifts the whole rest of the document, and a positional diff would show
// twenty-six mismatches where there are two. A panel that exaggerates losses is exactly as
// useless as one that hides them.
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

      <!-- Editing zone -->
      <section class="ds-section">
        <h6 class="mb-3">{{ t('design-system.section.markdown-editor.editor') }}</h6>
        <MarkdownEditor v-model="body" />
        <p class="ds-note mt-2">{{ t('design-system.section.markdown-editor.editorHint') }}</p>
      </section>

      <!-- Simple mode: the feature set as the field's contract -->
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

      <!-- Table: the only block that doesn't fit on one markdown line -->
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

      <!-- Diagram: a mermaid fence shown drawn, edited as source -->
      <section class="ds-section">
        <h6 class="mb-3">{{ t('design-system.section.markdown-editor.diagram') }}</h6>
        <MarkdownEditor v-model="diagramBody" min-height="220px" />
        <p class="ds-note mt-2">{{ t('design-system.section.markdown-editor.diagramHint') }}</p>

        <div class="pane-grid mt-4">
          <div class="pane">
            <span class="ds-tag mb-2">{{ t('design-system.section.markdown-editor.emitted') }}</span>
            <pre class="code-box code-box--short">{{ diagramBody }}</pre>
          </div>
          <div class="pane">
            <span class="ds-tag mb-2">{{ t('design-system.section.markdown-editor.noDiagram') }}</span>
            <MarkdownEditor v-model="codeOnlyBody" :features="CODE_ONLY" min-height="120px" />
          </div>
        </div>
      </section>

      <!-- Round trip -->
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

      <!-- Live output -->
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

      <!-- Coverage -->
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

/* The small example is as tall as its content: an empty panel a third of the screen high under a
   five-row table would read as "something failed to load here". */
.code-box--short {
  min-height: 0;
}

.preview-box {
  background: var(--surface);
  border: 1px solid var(--border-soft);
  border-radius: var(--radius);
  padding: 20px 24px;
}

/* ── Verdicts ─────────────────────────────────────────────── */

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

/* ── Diff ─────────────────────────────────────────────────── */

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
