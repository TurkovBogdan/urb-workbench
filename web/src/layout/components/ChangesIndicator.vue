<script setup lang="ts">
// Индикатор ленты изменений: мелкая светлая строка в правом верхнем углу.
//
// Нужен тому, кто знает, куда смотреть, — остальных отвлекать не должен. Поэтому он крошечный,
// серый, не ловит курсор и живёт ~2 секунды: крутилка и «что обновилось», потом гаснет. Показан
// всегда только последний случай — лента бывает частой, и очередь из сообщений превратила бы
// тихий признак в мерцание.
//
// Имя сущности показывается как есть (`tasks.task`): лента сущностей не знает, а подпись для
// каждой завёл бы каждый модуль — ради строки, на которую смотрят разработчик и агент.
import { onBeforeUnmount, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'

import { useChangesStore, type Change } from '@/stores/changes'

/** Сколько видна строка после последнего случая. */
const VISIBLE_MS = 2000

/** Сколько кодов показать; остальные — числом, иначе массовое изменение займёт полэкрана. */
const IDS_SHOWN = 1

const { t } = useI18n()
const changes = useChangesStore()

const text = ref('')
const visible = ref(false)
let timer: ReturnType<typeof setTimeout> | undefined

function describe(change: Change | null): string {
  if (!change) return t('common.changes.resync')
  const shown = change.ids.slice(0, IDS_SHOWN).join(', ')
  const more = change.ids.length > IDS_SHOWN ? ` +${change.ids.length - IDS_SHOWN}` : ''
  const ids = shown ? ` ${shown}${more}` : ''
  return `${t(`common.changes.event.${change.event}`)} · ${change.entity}${ids}`
}

watch(
  () => changes.latest?.seq,
  () => {
    if (!changes.latest) return
    text.value = describe(changes.latest.change)
    visible.value = true
    clearTimeout(timer)
    timer = setTimeout(() => { visible.value = false }, VISIBLE_MS)
  },
)

onBeforeUnmount(() => clearTimeout(timer))
</script>

<template>
  <!-- Для читалки — вежливое объявление: оно не перебивает, а договаривается, когда человек
       закончит. Видимое и произносимое — одна и та же строка. -->
  <Transition name="changes-indicator">
    <div v-if="visible" class="changes-indicator" role="status" aria-live="polite">
      <VProgressCircular indeterminate size="9" width="1.5" class="changes-indicator__spin" />
      <span class="changes-indicator__text">{{ text }}</span>
    </div>
  </Transition>
</template>

<style scoped>
/* Угол, а не поток страницы: строка висит над шапкой и ничего не сдвигает. Курсор она не ловит —
   под ней бывают кнопки шапки. */
.changes-indicator {
  position: fixed;
  top: 6px;
  right: 14px;
  z-index: 2000;
  display: inline-flex;
  align-items: center;
  gap: 5px;
  max-width: 50vw;
  font-family: var(--font);
  font-size: 10px;
  line-height: 12px;
  color: var(--text-faint);
  opacity: 0.8;
  pointer-events: none;
  user-select: none;
}

/* `!important` — против цвета, который крутилкам ставят умолчания темы (`plugins/vuetify.ts`,
   акцентный): здесь она обязана быть такой же серой, как текст, иначе оранжевая точка в углу
   тянет взгляд сильнее всей строки. */
.changes-indicator__spin {
  flex: none;
  color: var(--text-faint) !important;
}

.changes-indicator__text {
  min-width: 0;
  overflow: hidden;
  white-space: nowrap;
  text-overflow: ellipsis;
}

.changes-indicator-enter-active,
.changes-indicator-leave-active {
  transition: opacity 200ms ease;
}

.changes-indicator-enter-from,
.changes-indicator-leave-to {
  opacity: 0;
}
</style>
