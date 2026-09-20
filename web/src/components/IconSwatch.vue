<script setup lang="ts">
// Знак объекта одной плашкой: его иконка в его цвете. Пара «иконка + цвет» есть у пространства,
// у зоны, у полки исследований — и объект узнаётся по ней везде, где он упомянут: в карточке
// списка, в строке выбора, в шапке чужого списка. Плашка поэтому одна на всех, а её размер
// задаёт место, куда она поставлена.
//
// Доменных типов здесь нет намеренно (правило промоушена, docs/conventions/frontend.md): на входе
// два имени из общих реестров, и компонент не знает, чей знак рисует.
//
// Задаётся ШИРИНА, от неё считается размер иконки: плашка квадратная, и вторая величина была бы
// способом рассогласовать её саму с собой.
//
// Скругление при этом от ширины НЕ зависит: у системы две ступени радиуса (`--radius` 10px для
// карточек, `--radius-sm` 6px для кнопок и полей), и плашка — предмет второй ступени, какого бы
// она ни была размера. Считай мы радиус долей ширины, у каждого размера плашки получалось бы
// своё скругление — третья шкала помимо двух общих, и рядом с иконочной кнопкой в 6px плашка
// выглядела бы переслащённой.
import { computed } from 'vue'

import { colorVarsByName } from '@/shared/colors'
import { iconByName } from '@/shared/icons'

const ICON_SHARE_OF_WIDTH = 0.7

const props = withDefaults(defineProps<{
  /** Имя из реестра `shared/icons.ts`; пустое — запасная иконка. */
  icon: string
  /** Имя из реестра `shared/colors.ts`; пустое — акцент приложения. */
  color: string
  /** Сторона плашки в пикселях. */
  width?: number
}>(), {
  width: 22,
})

const iconSize = computed(() => Math.round(props.width * ICON_SHARE_OF_WIDTH))

const boxStyle = computed(() => ({
  '--icon-swatch-width': `${props.width}px`,
  ...colorVarsByName(props.color),
}))
</script>

<template>
  <span class="icon-swatch color-tones" :style="boxStyle">
    <component :is="iconByName(props.icon)" :size="iconSize" :stroke-width="1.7" />
  </span>
</template>

<style scoped>
.icon-swatch {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: var(--icon-swatch-width);
  height: var(--icon-swatch-width);
  border-radius: var(--radius-sm);
  flex: none;
  /* Цвет объекта, а без него — акцент приложения: тот же запасной путь, что у иконки. */
  color: var(--gc-ink, var(--accent));
  background: var(--gc-fill, var(--accent-soft));
}
</style>
