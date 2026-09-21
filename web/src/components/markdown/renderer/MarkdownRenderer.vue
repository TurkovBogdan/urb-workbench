<script setup lang="ts">
import { computed, getCurrentInstance, h, nextTick, onBeforeUnmount, onMounted, ref, render, watch } from 'vue'
import { useRouter } from 'vue-router'
import CodeBlock from '@/components/CodeBlock.vue'
import DiagramBlock from '@/components/DiagramBlock.vue'
import { useAfterRouteTransition } from '@/composables/useRouteTransition'
import { useSettingsStore } from '@/stores/settings'
import { renderMarkdown, type HeadingAnchor } from './render'

const router = useRouter()
const settings = useSettingsStore()

const props = defineProps<{
  text: string
  compact?: boolean
  // Документ целиком, а не подпись под полем: разбор и раскладка такого тела занимают главный
  // поток на десятки миллисекунд, и выпади они на переход между страницами — съели бы его
  // анимацию. Помеченное так тело ждёт конца перехода; всё остальное рисуется сразу.
  heavy?: boolean
  // Render Markdown images as <img> (off by default: the agent chat strips them).
  allowImages?: boolean
  // Treat single newlines as <br> — preserves line breaks of plain-text email bodies.
  breaks?: boolean
  // Map `TYPE@hash` → entity title. When a reference pill's code resolves here, the pill
  // shows the (truncated) title instead of the short hash.
  refLabels?: Record<string, string>
}>()

const REF_LABEL_MAX = 48

const emit = defineEmits<{
  imageClick: [src: string]
  // Оглавление тела: заголовки с проставленными `id`. Отдаём событием, а не через expose —
  // потребителю (боковой навигации) нужен готовый список, а не доступ внутрь рендерера.
  headings: [items: HeadingAnchor[]]
}>()

// Swap each reference pill's label from the short hash to the resolved entity title
// (truncated). Runs on the already-sanitized HTML; textContent/setAttribute escape, so no
// re-sanitize is needed. The href/code stay untouched. Key = `TYPE@hash` (last href segment).
function withRefLabels(sanitized: string): string {
  const labels = props.refLabels
  if (!labels || typeof window === 'undefined') return sanitized
  const doc = new DOMParser().parseFromString(sanitized, 'text/html')
  let changed = false
  doc.querySelectorAll('a.md-ref').forEach((a) => {
    const code = (a.getAttribute('href') ?? '').split('/').pop() ?? ''
    const title = labels[code]
    const label = a.querySelector('.md-ref-label')
    if (!title || !label) return
    label.textContent = title.length > REF_LABEL_MAX ? title.slice(0, REF_LABEL_MAX) + '…' : title
    a.setAttribute('title', title)
    changed = true
  })
  return changed ? doc.body.innerHTML : sanitized
}

// Пустой текст, пока идёт переход, — это и есть отсрочка: разбор не запускается, оглавление
// приезжает вместе с телом, и ни один потребитель не узнаёт про ожидание ничего сверх того,
// что тело пока пустое.
const settled = useAfterRouteTransition()

const source = computed(() => (props.heavy && !settled.value ? '' : props.text))

const rendered = computed(() => renderMarkdown(source.value, {
  breaks: props.breaks ?? false,
  allowImages: props.allowImages ?? false,
}))

const html = computed(() => withRefLabels(rendered.value.html))

watch(() => rendered.value.headings, (items) => emit('headings', items), { immediate: true })

// Code blocks are not part of the HTML: the parser leaves an empty slot for each one and the
// real component is mounted into it here, so a body gets highlighting, a copy button and a
// language badge. A one-liner takes the compact variant — a command reads as a chip, not as a
// panel with a header. A `mermaid` fence is a diagram instead: the same slot, another component.
const DIAGRAM_LANGUAGE = 'mermaid'

const body = ref<HTMLElement | null>(null)
const appContext = getCurrentInstance()?.appContext ?? null
let mountedSlots: HTMLElement[] = []

function unmountCodeBlocks() {
  for (const slot of mountedSlots) render(null, slot)
  mountedSlots = []
}

// Повторный вызов на том же теле — не пересборка, а обновление: `render` в тот же слот с тем же
// компонентом правит пропы, поэтому смена настройки нумерации доезжает до блоков без повторной
// подсветки. Список слотов собирается заново, иначе на каждом вызове в нём копились бы дубли.
function mountCodeBlocks() {
  const container = body.value
  if (!container) return
  mountedSlots = []
  container.querySelectorAll<HTMLElement>('.md-code-slot').forEach((slot) => {
    const block = rendered.value.codeBlocks[Number(slot.dataset.codeIndex)]
    if (!block) return
    const code = block.code.replace(/\n$/, '')
    const isOneLiner = !block.code.trim().includes('\n')
    const vnode = block.language === DIAGRAM_LANGUAGE
      ? h(DiagramBlock, { code })
      : h(CodeBlock, {
          code,
          lang: block.language || undefined,
          // Однострочник — командная плашка независимо от выбранного вида: он про содержимое,
          // а не про оформление.
          variant: isOneLiner ? 'compact' : settings.typography.codeVariant,
          showLineNumbers: settings.typography.codeLineNumbers,
        })
    vnode.appContext = appContext
    render(vnode, slot)
    mountedSlots.push(slot)
  })
}

watch(
  () => [settings.typography.codeVariant, settings.typography.codeLineNumbers],
  () => mountCodeBlocks(),
)

// v-html replaces the container's children, so the previous instances are unmounted first —
// while their slots (detached by then or not) are still known here.
watch(html, () => {
  unmountCodeBlocks()
  nextTick(mountCodeBlocks)
})

onMounted(mountCodeBlocks)
onBeforeUnmount(unmountCodeBlocks)

function onClick(event: MouseEvent) {
  const anchor = (event.target as HTMLElement).closest('a')
  if (anchor) {
    const href = anchor.getAttribute('href') ?? ''
    // Internal links (source citations et al.) navigate via the router — no full reload.
    // Modifier-click falls through to the browser so open-in-new-tab keeps working.
    if (href.startsWith('/') && !event.metaKey && !event.ctrlKey && !event.shiftKey) {
      event.preventDefault()
      router.push(href)
    }
    return
  }
  if (!props.allowImages) return
  const image = (event.target as HTMLElement).closest('img')
  if (image) emit('imageClick', (image as HTMLImageElement).currentSrc || image.getAttribute('src') || '')
}
</script>

<template>
  <div ref="body" class="md-body" :class="{ 'md-body--compact': compact }" v-html="html" @click="onClick" />
</template>

<!-- Типографика тела живёт в общем файле и обслуживает обе зоны — просмотр и правку. Своего
     scoped-блока у рендерера больше нет: вторая копия этих правил и была тем, что разошлось. -->
<style src="../shared/document.css"></style>
