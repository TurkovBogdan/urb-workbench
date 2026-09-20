<script setup lang="ts">
// «Забрать код объекта» — одна кнопка на все шапки: и на деталках (`DetailHead`), и на страницах,
// чья шапка страничная (`PageHeader` у полки). Раньше разметка жила в `DetailHead`, и полка
// повторила бы её слово в слово — а расходятся такие копии молча, по одной правке за раз.
//
// Подпись обязательна там, где кнопка стоит рядом с ИМЕНЕМ объекта: значок копирования сам по себе
// не говорит, что именно он заберёт, и ответ должен читаться, а не угадываться. Когда кнопка стоит
// вплотную к самому коду (шапка деталки), вопроса «что копируется» уже нет — там она сжимается до
// значка (`icon`), а подпись уходит в подсказку.
import { useI18n } from 'vue-i18n'
import { IconCheck, IconCopy } from '@tabler/icons-vue'

import { useClipboard } from '@/composables/useClipboard'

withDefaults(defineProps<{
  code: string
  /** Только значок: код написан рядом и говорит за кнопку сам. */
  icon?: boolean
}>(), {
  icon: false,
})

const { t } = useI18n()
const { copy, isCopied } = useClipboard()
</script>

<template>
  <!-- Ответ об успехе даёт только значок: подпись говорит, что кнопка делает, и меняться от
       нажатия ей незачем — иначе кнопка на мгновение перестаёт быть той же самой, а вместе с
       длиной подписи дёргается и весь ряд. -->
  <VBtn
    v-if="icon"
    icon
    variant="text"
    size="small"
    class="copy-code__icon"
    :title="t('common.action.copy_code')"
    :aria-label="t('common.action.copy_code')"
    @click="copy(code)"
  >
    <IconCheck v-if="isCopied(code)" :size="15" class="copy-code__done" />
    <IconCopy v-else :size="15" />
  </VBtn>

  <VBtn v-else variant="text" @click="copy(code)">
    <template #prepend>
      <IconCheck v-if="isCopied(code)" :size="16" class="copy-code__done" />
      <IconCopy v-else :size="16" />
    </template>
    {{ t('common.action.copy_code') }}
  </VBtn>
</template>

<style scoped>
/* Об успехе говорит сама смена значка, и цветом его называть незачем: копирование кода — рядовое
   действие, которое делают по многу раз, а зелёная вспышка в шапке читается как событие. Серый
   держит галочку в том же весе, что и значок, который она подменила. */
.copy-code__done {
  color: var(--text-muted);
}

/* Значок стоит в строке кода, а не в ряду кнопок: его коробка сжата до высоты этой строки, и
   веса он того же, что и текст рядом, — до наведения кнопки там не видно вовсе. */
.copy-code__icon {
  width: 22px;
  height: 22px;
  color: var(--text-faint);
}

.copy-code__icon:hover { color: var(--text); }
</style>
