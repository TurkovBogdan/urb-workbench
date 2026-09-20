<script setup lang="ts">
// Шапка модального окна: заголовок, необязательное описание, крестик и линия к контенту — по
// образцу формы оплаты. Линию держит шапка, а не контент: контентных блоков у окна бывает
// несколько (колонки чекаута, вкладки), шапка одна, и линия не должна зависеть от того, что под ней.
import { IconX } from '@tabler/icons-vue'
import { useI18n } from 'vue-i18n'

// Крестик рисуется ВСЕГДА и пропом не выключается: выход из окна не бывает необязательным, а
// у блокирующего он и вовсе единственный. Родитель обязан слушать `close`.
withDefaults(defineProps<{
  title: string
  /** Подзаголовок под заголовком. Без него шапка однострочная, линия остаётся. */
  description?: string
  /** Линия к контенту. Снимать только у окна БЕЗ контентного блока (`ConfirmDialog`). */
  rule?: boolean
  /** Идёт работа: закрывать нельзя, но крестик остаётся видимым. */
  closeDisabled?: boolean
}>(), {
  description: undefined,
  rule: true,
  closeDisabled: false,
})

const emit = defineEmits<{ (e: 'close'): void }>()

const { t } = useI18n()
</script>

<template>
  <header class="dlg-head" :class="{ 'dlg-head--rule': rule }">
    <!-- Заголовок и описание отдаются слотами: в деталке заголовок — правимое поле, а под ним
         рядом с кодом стоит кнопка. Пропы при этом остаются главным путём: слот нужен там, где
         строка перестала быть строкой, и заводить ради этого второй компонент шапки незачем. -->
    <div class="dlg-head__text">
      <slot name="title">
        <h2 class="dlg-head__title">{{ title }}</h2>
      </slot>
      <slot name="description">
        <p v-if="description" class="dlg-head__description">{{ description }}</p>
      </slot>
    </div>

    <!-- Действия стоят ПРАВЕЕ крестика: выход из окна — движение в его левый край, к содержимому,
         а действия над самим содержимым продолжают ряд наружу. -->
    <div class="dlg-head__tools">
      <VBtn
        icon
        variant="text"
        :disabled="closeDisabled"
        :title="t('common.action.close')"
        @click="emit('close')"
      >
        <IconX :size="18" />
      </VBtn>

      <slot name="actions" />
    </div>
  </header>
</template>

<style scoped>
/* Отступы и кегль сняты с формы оплаты — она и была образцом. */
.dlg-head {
  /* Крестик выше строки заголовка и без описания растил бы шапку на пустое место. Обе величины
     держим рядом: бокс кнопки задан явно, отрицательные поля ровно на разницу выводят её из
     расчёта высоты. Крестик встаёт по центру строки заголовка, высоту шапки задаёт текст. */
  --dlg-close-size: 42px;
  --dlg-title-line: 24px;
  --dlg-pad-y: 22px;
  --dlg-pad-x: 24px;
  --dlg-close-shift: calc((var(--dlg-title-line) - var(--dlg-close-size)) / 2);

  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
  padding: var(--dlg-pad-y) var(--dlg-pad-x) 18px;
}

.dlg-head--rule { border-bottom: 1px solid var(--border-soft); }

/* Текстовая половина забирает всё, что осталось от ряда действий: в ней может стоять поле, а оно
   без этого тянулось бы по своему содержимому. */
.dlg-head__text {
  flex: 1;
  min-width: 0;
}

.dlg-head__title {
  margin: 0;
  font-size: 18px;
  line-height: var(--dlg-title-line);
  font-weight: 700;
  color: var(--text);
}

.dlg-head__description { margin: 4px 0 0; font-size: 13px; color: var(--text-muted); }

/* Отрицательные поля держит РЯД, а не крестик: действий в нём может быть сколько угодно, а из
   расчёта высоты шапки выводится весь ряд целиком. */
.dlg-head__tools {
  display: flex;
  align-items: center;
  flex: none;
  margin-block: var(--dlg-close-shift);
  /* Вправо ровно настолько, чтобы кромка крайней кнопки отстояла от правого края так же, как от
     верхнего: сверху ряд уже сдвинут на --dlg-close-shift. */
  margin-right: calc(var(--dlg-pad-y) + var(--dlg-close-shift) - var(--dlg-pad-x));
}

/* Бокс задан явно: у иконочной кнопки он зависит от `density`, а здесь от него зависит сдвиг
   всего ряда. Слотовым действиям он достаётся тем же правилом — ряд обязан стоять по одной оси. */
.dlg-head__tools :deep(.v-btn) {
  width: var(--dlg-close-size);
  height: var(--dlg-close-size);
}
</style>
