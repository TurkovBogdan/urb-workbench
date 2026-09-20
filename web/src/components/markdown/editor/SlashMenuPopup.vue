<script setup lang="ts">
// The popup half of the slash menu. Plain Vuetify: the menu inherits the application's theme,
// density and focus styling because it is made of the same parts as the rest of the interface.
import { computed, nextTick, ref, watch } from 'vue'
import { shortcutLabels } from './slashMenu'
import type { SlashController, SlashState } from './slashMenu'

const props = defineProps<{ state: SlashState; controller: SlashController }>()

const MENU_HEIGHT = 320

const scroller = ref<HTMLElement | null>(null)

// Доводка до активного пункта. Клавиатурная навигация уводит выбор за нижний край списка, и
// без этого человек жмёт стрелку в пустоту: подсветка ушла туда, где её не видно.
// `block: 'nearest'` прокручивает ровно настолько, чтобы пункт стал виден, и не дёргает
// список, когда он и так на экране.
watch(() => props.state.active, async (index) => {
  await nextTick()
  scroller.value?.querySelector(`[data-index="${index}"]`)?.scrollIntoView({ block: 'nearest' })
})

// Новый запрос — список другой: прокрутку возвращаем в начало, иначе первый пункт окажется
// выше видимой области.
watch(() => props.state.items, async () => {
  await nextTick()
  if (scroller.value) scroller.value.scrollTop = 0
})

// Flip above the caret near the bottom of the viewport. `position: fixed` puts the menu
// outside the editor's scroll box, so it never clips against the page column.
const above = computed(() => props.state.top + MENU_HEIGHT > window.innerHeight)

const style = computed(() => ({
  left: `${props.state.left}px`,
  ...(above.value
    ? { bottom: `${window.innerHeight - props.state.bottom + 6}px` }
    : { top: `${props.state.top + 6}px` }),
}))
</script>

<template>
  <Teleport to="body">
    <div v-if="state.open && state.items.length" class="slash" :style="style">
      <VCard elevation="8" rounded="lg" class="slash__card">
        <div ref="scroller" class="slash__scroll">
          <VList density="compact" nav class="py-1">
            <template v-for="(item, index) in state.items" :key="item.id">
              <!-- Черта между группами: типы блоков читаются отдельными наборами, а не одной
                   простынёй. Рисуется перед первым пунктом группы, кроме самой первой. -->
              <VDivider v-if="index > 0 && item.group !== state.items[index - 1].group" class="my-1" />
              <VListItem
                :data-index="index"
                :active="index === state.active"
                color="primary"
                @click="controller.pick(index)"
              >
                <template #prepend>
                  <component :is="item.icon" :size="17" class="slash__icon" />
                </template>
                <VListItemTitle class="slash__title">{{ item.title }}</VListItemTitle>
                <template #append>
                  <span v-if="item.keys" class="slash__keys">
                    <kbd v-for="key in shortcutLabels(item.keys)" :key="key" class="slash__key">{{ key }}</kbd>
                  </span>
                </template>
              </VListItem>
            </template>
          </VList>
        </div>
      </VCard>
    </div>
  </Teleport>
</template>

<style scoped>
.slash {
  position: fixed;
  z-index: 2400;
  width: 320px;
}

/* Прокрутка живёт на внутреннем слое, а скругление и обрезка — на карточке. Иначе список
   едет поверх скруглённых углов: полоса прокрутки и последний пункт упираются в прямой край. */
.slash__card {
  overflow: hidden;
}

.slash__scroll {
  max-height: 320px;
  overflow-y: auto;
  /* Докрутив список до конца, не прокручиваем страницу под ним. */
  overscroll-behavior: contain;
}

.slash__title {
  font-size: 13px;
}

/* Отступ задаём сами: Vuetify разносит слот только для своих VIcon/VAvatar, а здесь иконка —
   обычный компонент, и по умолчанию она прилипает к подписи. */
.slash__icon {
  color: var(--text-muted);
  margin-right: 10px;
}

/* Подписи клавиш — отдельными плашками, как их рисует система: сплошная строка «Ctrl Alt 1»
   читается как текст, а не как сочетание. */
.slash__keys {
  display: inline-flex;
  align-items: center;
  gap: 3px;
  padding-left: 16px;
}

.slash__key {
  font-family: var(--font-mono);
  font-size: 10px;
  line-height: 1;
  color: var(--text-faint);
  background: color-mix(in srgb, rgb(var(--v-theme-on-surface)) 6%, transparent);
  border: 1px solid var(--border-soft);
  border-radius: 3px;
  padding: 2px 4px;
  min-width: 16px;
  text-align: center;
}
</style>
