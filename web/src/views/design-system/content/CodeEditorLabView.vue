<script setup lang="ts">
// Stand: the editor's code block under load. Not part of the showcase index — reached by its
// address only. It builds a bare editor around the production node (blocks/codeBlock.ts) so the
// highlight passes can be timed: each pass reports through `onStats`, which the real editor leaves
// unset.
import { computed, reactive, ref } from 'vue'
import { EditorContent, useEditor } from '@tiptap/vue-3'
import StarterKit from '@tiptap/starter-kit'
import PageLayout from '@/layout/templates/PageLayout.vue'
import PageHeader from '@/layout/components/PageHeader.vue'
import MarkdownRenderer from '@/components/markdown/renderer/MarkdownRenderer.vue'
import { docToMarkdown, markdownToDoc } from '@/components/markdown/editor'
import { CodeBlock, Diagram, EntityRef, FlatBlocks } from '@/components/markdown/editor/blocks'
import { tokenCounters } from '@/composables/useHighlighter'
import type { HighlightStats } from '@/components/markdown/editor/blocks/codeHighlight'
import SAMPLE from './code-editor-lab/sample.md?raw'

type View = 'editor' | 'renderer' | 'markdown'

const view = ref<View>('editor')
const markdown = ref(SAMPLE)

const stats = reactive<HighlightStats & { tokenized: number; cacheHits: number; typingMaxMs: number }>({
  lastMs: 0, maxMs: 0, blocks: 0, decorations: 0, full: true, deferred: 0, tokenized: 0, cacheHits: 0, typingMaxMs: 0,
})

// A full pass runs on load and when a language arrives; what a person feels is the partial pass
// behind each keystroke, so its worst case is kept apart.
function onStats(next: HighlightStats): void {
  Object.assign(stats, next, tokenCounters)
  if (!next.full) stats.typingMaxMs = Math.max(stats.typingMaxMs, next.lastMs)
}

const editor = useEditor({
  content: markdownToDoc(SAMPLE),
  editorProps: { attributes: { class: 'md-body lab-editor__doc' } },
  extensions: [
    StarterKit.configure({
      codeBlock: false,
      underline: false,
      blockquote: false,
      bulletList: false,
      orderedList: false,
      listItem: false,
      listKeymap: false,
      code: { HTMLAttributes: { class: 'md-codespan' } },
      link: { openOnClick: false, autolink: true },
    }),
    FlatBlocks,
    EntityRef,
    Diagram,
    CodeBlock.configure({ onStats }),
  ],
  onUpdate: ({ editor: current }) => {
    markdown.value = docToMarkdown(current.getJSON())
  },
})

function load(text: string): void {
  markdown.value = text
  editor.value?.commands.setContent(markdownToDoc(text))
  stats.typingMaxMs = 0
}

function longBlock(lines: number): string {
  const body = Array.from({ length: lines }, (_, i) =>
    `def handler_${i}(order: Order, retries: int = ${i % 7}) -> str | None:  # line ${i + 1}\n` +
    `    return f"order {order.id} -> {retries}" if order.items else None`,
  ).join('\n')
  return `# Длинный блок\n\nPython, ${lines * 2} строк.\n\n\`\`\`python\n${body}\n\`\`\`\n`
}

const statsLine = computed(() =>
  `проход ${stats.lastMs.toFixed(1)} мс (${stats.full ? 'полный' : 'частичный'}, блоков ${stats.blocks}, ждут паузы ${stats.deferred}) · ` +
  `максимум ${stats.maxMs.toFixed(1)} мс, при наборе ${stats.typingMaxMs.toFixed(1)} мс · ` +
  `декораций ${stats.decorations} · ` +
  `токенизаций ${stats.tokenized}, из кэша ${stats.cacheHits}`,
)
</script>

<template>
  <PageLayout>
    <div class="ds-page lab">
      <PageHeader
        title="Стенд: редактируемый блок кода"
        description="Рабочий узел блока кода в голом редакторе, с замерами каждого прохода подсветки."
        back-to="/design-system"
      />

      <div class="lab__toolbar">
        <VBtnToggle v-model="view" mandatory divided density="compact">
          <VBtn value="editor">Редактор</VBtn>
          <VBtn value="renderer">Просмотр</VBtn>
          <VBtn value="markdown">Markdown</VBtn>
        </VBtnToggle>
        <VSpacer />
        <VBtn variant="text" size="small" @click="load(SAMPLE)">Статья</VBtn>
        <VBtn variant="text" size="small" @click="load(longBlock(500))">1000 строк</VBtn>
        <VBtn variant="text" size="small" @click="load(longBlock(2500))">5000 строк</VBtn>
      </div>

      <p class="lab__stats">{{ statsLine }}</p>

      <VCard class="lab__card" variant="outlined" rounded="lg">
        <EditorContent v-show="view === 'editor'" :editor="editor" />
        <MarkdownRenderer v-if="view === 'renderer'" :text="markdown" />
        <pre v-if="view === 'markdown'" class="lab__markdown">{{ markdown }}</pre>
      </VCard>
    </div>
  </PageLayout>
</template>

<style scoped>
.lab {
  max-width: 920px;
}

.lab__toolbar {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 8px;
}

.lab__stats {
  font-family: var(--font-mono);
  font-size: 11px;
  color: var(--text-muted);
  margin-bottom: 12px;
}

.lab__card {
  padding: 20px 24px;
}

.lab__card :deep(.lab-editor__doc) {
  outline: none;
}

.lab__markdown {
  white-space: pre-wrap;
  max-height: 70vh;
}
</style>
