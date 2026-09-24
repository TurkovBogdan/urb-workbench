<script setup lang="ts">
// Плашка копирования: значок копирования и текст — одна кнопка.
//
// Значок стоит ПЕРВЫМ: он говорит, что это за плашка, раньше, чем глаз дочитает значение, и не
// уезжает вслед за длиной текста — у плашек разной длины значки стоят в одну линию.
//
// Для всего, что человек забирает в буфер ради того, чтобы вставить в другое место: код объекта,
// адрес, токен, путь. Раньше рядом с текстом стояла отдельная кнопка-значок 22px, и в неё
// приходилось целиться, хотя сам текст рядом не делал ничего. Здесь мишень — вся плашка, и
// скопировано ровно то, что на ней написано (или `text`, если показывается другое).
//
// В покое плашка прозрачна и читается как обычный текст: копирование — побочное действие, и звать
// к себе ему незачем. Кнопкой её выдаёт подложка под курсором — та же, что у кнопки-счётчика.
// Об успехе говорит смена значка на галочку, без цвета: копирование делают по многу раз, и
// зелёная вспышка читалась бы как событие.
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { IconCheck, IconCopy } from '@tabler/icons-vue'

import { useClipboard } from '@/composables/useClipboard'

const props = defineProps<{
  /** Что уходит в буфер. */
  text: string
  /** Что написано на плашке; не передано — сам `text`. */
  label?: string
  /** Подпись действия для подсказки и читалки; по умолчанию «Скопировать». */
  hint?: string
}>()

const { t } = useI18n()
const { copy, isCopied } = useClipboard()

const copied = computed(() => isCopied(props.text))
const hintText = computed(() =>
  copied.value ? t('common.action.copied') : (props.hint ?? t('common.action.copy')),
)
</script>

<template>
  <!-- Клик дальше плашки не уходит: она стоит и в строках, которые открываются по клику, и
       «скопировать» не должно заодно уводить со страницы. -->
  <button
    type="button"
    class="copy-chip"
    :aria-label="`${hintText}: ${props.label ?? props.text}`"
    @click.stop="copy(props.text)"
  >
    <IconCheck v-if="copied" :size="14" :stroke-width="1.8" class="copy-chip__icon" />
    <IconCopy v-else :size="14" :stroke-width="1.6" class="copy-chip__icon" />
    <span class="copy-chip__text">{{ props.label ?? props.text }}</span>
    <VTooltip activator="parent" location="top">{{ hintText }}</VTooltip>
  </button>
</template>

<style scoped>
/* Вид — от кнопки-счётчика (`CounterButton.vue`): шрифт интерфейса, мелкий кегль, приглушённый
   цвет, подложка только под курсором. Гарнитура — `--font`, а не наследованная: плашка стоит и в
   шапках, и в строках, и должна выглядеть одинаково везде, где её поставили.

   Текст и значок в коробках одной высоты (14px): при разных высотах flex даёт дробные смещения,
   браузер округляет их по-разному, и текст встаёт на пиксель выше значка. */
.copy-chip {
  display: inline-flex;
  flex: none;
  align-items: center;
  gap: 4px;
  max-width: 100%;
  height: 22px;
  padding: 0 5px;
  border: 0;
  border-radius: 6px;
  background: transparent;
  font-family: var(--font);
  font-size: 12px;
  font-weight: 400;
  line-height: 14px;
  letter-spacing: normal;
  color: var(--copy-chip-color, var(--text-muted));
  cursor: pointer;
  transition: background-color 120ms ease, color 120ms ease;
}

.copy-chip:hover,
.copy-chip:focus-visible {
  background: var(--border-soft);
  color: var(--text);
  outline: none;
}

/* Длинное значение (путь, токен) сжимается многоточием, значок — никогда: без него плашка
   перестаёт говорить, что по ней можно нажать. */
.copy-chip__text {
  min-width: 0;
  overflow: hidden;
  white-space: nowrap;
  text-overflow: ellipsis;
}

/* Значок тише текста: он поясняет действие, а не называет значение. */
.copy-chip__icon {
  flex: none;
  color: var(--text-faint);
}

.copy-chip:hover .copy-chip__icon,
.copy-chip:focus-visible .copy-chip__icon {
  color: inherit;
}
</style>
