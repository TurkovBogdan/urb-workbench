<script setup lang="ts">
// Кнопка-счётчик: значок, число и стрелка сворачивания — одна мишень.
//
// Одна на всё приложение: её носят и строка задачи с подзадачами, и шапка карточки группы. Пока
// стилей было два, они разъехались — счёт группы набирался иначе, чем счёт строки, и соседние
// кнопки читались разными предметами. Отличаются места применения только значком и подписью.
//
// Всё собрано в одну кнопку, потому что по отдельности стрелка — мишень 20px, в которую трудно
// попасть, а значок и число рядом с ней выглядят нажимаемыми и ничего не делают. Счёт стоит
// первым: он отвечает на вопрос, стоит ли разворачивать.
//
// Клик и Enter дальше кнопки не уходят: строка задачи по ним открывает задачу, а свернуть ветку
// и уйти со списка одним нажатием — не то, что человек просил.
import type { Component } from 'vue'
import { IconChevronDown, IconChevronRight } from '@tabler/icons-vue'

const props = defineProps<{
  /** Что считаем: подзадачи у строки, задачи у группы. */
  icon: Component
  /** Не передан — числа нет, остаются значок и стрелка. Ноль показывается: это тоже ответ. */
  count?: number
  /** Содержимое свёрнуто: стрелка смотрит вбок, туда, откуда оно выедет. */
  folded: boolean
  /** Подпись действия — для читалки и для подсказки; зависит от `folded`, её знает вызывающий. */
  label: string
}>()

const emit = defineEmits<{ toggle: [] }>()
</script>

<template>
  <button
    type="button"
    class="counter-button"
    :aria-expanded="!props.folded"
    :aria-label="props.label"
    @click.stop="emit('toggle')"
    @keydown.enter.stop
  >
    <component :is="props.icon" :size="14" :stroke-width="1.6" />
    <span v-if="props.count !== undefined" class="counter-button__number">{{ props.count }}</span>
    <component :is="props.folded ? IconChevronRight : IconChevronDown" :size="14" :stroke-width="1.8" />
    <VTooltip activator="parent" location="top">{{ props.label }}</VTooltip>
  </button>
</template>

<style scoped>
/* Выглядит пометкой, а не кнопкой: мелкий кегль и приглушённый цвет. Кнопкой её выдаёт только
   подложка под курсором — поле вокруг значков и есть мишень. Шрифт сбрасывается целиком: кнопка
   стоит и в полужирном имени группы, и в обычной строке, и наследовать там ей нечего. Гарнитура —
   шрифт интерфейса (`--font`), а не наследованная и не названная по имени: его выбирает человек
   в настройках, и кнопка обязана меняться вместе с остальным интерфейсом.

   Число — 11px обычными цифрами. Сравнивали вживую с 12px и цифрами одной ширины
   (`tabular-nums`) и с моноширинным: табличные цифры широкие и рядом с 13px названием выглядят
   грубо, моноширинный читается чужеродно. Кнопка при смене числа чуть меняет
   ширину — это дешевле, чем грубые цифры в каждой строке.

   Цвет в покое задаёт место применения через `--counter-button-color`: и строка, и карточка
   проявляют кнопку, когда курсор над ними, а не только над ней самой. Переменная, а не
   правило снаружи: чужое правило со своим весом перебивало бы наведение на саму кнопку.

   Все три части — в коробке одной высоты, 14px: и значки, и строка числа (`line-height`).
   Центрирует их flex, и при разных высотах смещение внутри кнопки выходит дробным (у 11px
   строки — 5.5px, у 13px стрелки — 4.5px). Браузер округляет такие смещения по-разному, и на
   экране число вставало на пиксель выше значка. С равными коробками смещение у всех целое и
   одно и то же. */
.counter-button {
  display: inline-flex;
  flex: none;
  align-items: center;
  gap: 3px;
  height: 22px;
  padding: 0 4px;
  border: 0;
  border-radius: 6px;
  background: transparent;
  font-family: var(--font);
  font-size: 11px;
  font-weight: 400;
  line-height: 14px;
  letter-spacing: normal;
  color: var(--counter-button-color, var(--text-faint));
  cursor: pointer;
  transition: background-color 120ms ease, color 120ms ease;
}

.counter-button:hover,
.counter-button:focus-visible {
  background: var(--border-soft);
  color: var(--text);
  outline: none;
}
</style>
