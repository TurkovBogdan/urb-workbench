<script setup lang="ts">
// Панель таблицы: появляется, когда каретка внутри неё, и исчезает, когда вышла.
//
// Почему отдельный компонент, а не кнопки в BubbleToolbar: та панель живёт над ВЫДЕЛЕНИЕМ и без
// него не показывается, а править колонки и ряды нужно при обычной каретке. Привязка тоже
// другая — не к выделенному тексту, а к самой таблице: действия относятся к ней целиком.
//
// Ряды добираются и без панели — Tab из последней ячейки и Enter из последнего ряда заводят
// новый, как в любом текстовом процессоре. Колонки и выравнивание иначе недостижимы, поэтому
// они здесь и есть главная причина панели существовать.
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import type { Editor } from '@tiptap/core'
import {
  IconAlignLeft, IconAlignCenter, IconAlignRight, IconAlignJustified,
  IconColumnInsertRight, IconColumnRemove,
  IconRowInsertBottom, IconRowRemove, IconTrash,
} from '@tabler/icons-vue'
import { activeColumnAlign, activeTable, type ColumnAlign } from '../blocks'

const props = defineProps<{ editor: Editor | undefined; tick: number }>()

const { t } = useI18n()

const MARGIN = 6

const spot = ref<{ right: number; top: number } | null>(null)

function place(): void {
  const editor = props.editor
  if (!editor || editor.isDestroyed) return hide()

  const found = activeTable(editor.state)
  if (!found) return hide()

  // Элемент берём у самого узла, а не у выделения: панель привязана к таблице, и при переходе
  // между ячейками она обязана стоять на месте, а не прыгать за кареткой.
  const dom = editor.view.nodeDOM(found.pos)
  if (!(dom instanceof HTMLElement)) return hide()

  const rect = dom.getBoundingClientRect()
  spot.value = { right: window.innerWidth - rect.right, top: rect.top }
}

function hide(): void {
  spot.value = null
}

const style = computed(() => {
  const at = spot.value
  if (!at) return {}
  return { right: `${at.right}px`, top: `${at.top}px`, transform: `translateY(calc(-100% - ${MARGIN}px))` }
})

// Выделение не переживёт перевода фокуса, поэтому кнопки не должны его забирать: mousedown
// гасится, клик доходит, каретка остаётся в своей ячейке.
function hold(event: Event): void {
  event.preventDefault()
}

watch(() => props.tick, place)
watch(() => props.editor, place)

onMounted(() => {
  place()
  window.addEventListener('scroll', place, true)
  window.addEventListener('resize', place)
})

onBeforeUnmount(() => {
  window.removeEventListener('scroll', place, true)
  window.removeEventListener('resize', place)
})

const align = computed<ColumnAlign>(() => {
  void props.tick
  return props.editor ? activeColumnAlign(props.editor.state) : null
})

function chain() {
  return props.editor?.chain().focus()
}

function setAlign(value: ColumnAlign): void {
  // Повторное нажатие снимает выравнивание: у колонки есть состояние «не задано», и добраться
  // до него надо той же кнопкой, которой его поставили.
  chain()?.setColumnAlign(align.value === value ? null : value).run()
}
</script>

<template>
  <Teleport to="body">
    <div v-show="spot" class="table-bar" :style="style" @mousedown="hold">
      <VCard elevation="8" rounded="lg" class="table-bar__card">
        <button class="table-bar__btn" :title="t('common.editor.table.column_after')" @click="chain()?.addColumnAfter().run()">
          <IconColumnInsertRight :size="16" />
        </button>
        <button class="table-bar__btn" :title="t('common.editor.table.column_delete')" @click="chain()?.deleteColumn().run()">
          <IconColumnRemove :size="16" />
        </button>

        <span class="table-bar__sep" />

        <button class="table-bar__btn" :title="t('common.editor.table.row_after')" @click="chain()?.addRowAfter().run()">
          <IconRowInsertBottom :size="16" />
        </button>
        <button class="table-bar__btn" :title="t('common.editor.table.row_delete')" @click="chain()?.deleteRow().run()">
          <IconRowRemove :size="16" />
        </button>

        <span class="table-bar__sep" />

        <button
          class="table-bar__btn"
          :class="{ 'is-on': align === null }"
          :title="t('common.editor.table.align_default')"
          @click="setAlign(null)"
        >
          <IconAlignJustified :size="16" />
        </button>
        <button class="table-bar__btn" :class="{ 'is-on': align === 'left' }" :title="t('common.editor.table.align_left')" @click="setAlign('left')">
          <IconAlignLeft :size="16" />
        </button>
        <button class="table-bar__btn" :class="{ 'is-on': align === 'center' }" :title="t('common.editor.table.align_center')" @click="setAlign('center')">
          <IconAlignCenter :size="16" />
        </button>
        <button class="table-bar__btn" :class="{ 'is-on': align === 'right' }" :title="t('common.editor.table.align_right')" @click="setAlign('right')">
          <IconAlignRight :size="16" />
        </button>

        <span class="table-bar__sep" />

        <button class="table-bar__btn table-bar__btn--danger" :title="t('common.editor.table.delete')" @click="chain()?.deleteTable().run()">
          <IconTrash :size="16" />
        </button>
      </VCard>
    </div>
  </Teleport>
</template>

<style scoped>
.table-bar {
  position: fixed;
  z-index: 2500;
}

.table-bar__card {
  display: flex;
  align-items: center;
  gap: 1px;
  padding: 3px 5px;
  height: 36px;
}

.table-bar__btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-width: 26px;
  height: 26px;
  padding: 0 4px;
  border: none;
  border-radius: 6px;
  background: none;
  color: var(--text-muted);
  cursor: pointer;
  transition: background 0.12s ease, color 0.12s ease;
}

.table-bar__btn:hover {
  background: color-mix(in srgb, rgb(var(--v-theme-on-surface)) 9%, transparent);
  color: var(--text);
}

.table-bar__btn.is-on {
  color: rgb(var(--v-theme-primary));
}

.table-bar__btn--danger:hover {
  background: color-mix(in srgb, rgb(var(--v-theme-error)) 12%, transparent);
  color: rgb(var(--v-theme-error));
}

.table-bar__sep {
  width: 1px;
  height: 16px;
  margin: 0 4px;
  background: var(--border-soft);
}
</style>
