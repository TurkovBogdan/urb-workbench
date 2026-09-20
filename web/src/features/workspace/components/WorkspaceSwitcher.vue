<script setup lang="ts">
// Выбор текущего пространства — первый элемент боковой панели.
//
// Пространство — это КОНТЕКСТ, а не место: смена пункта ничего не открывает и никуда не ведёт,
// она лишь отвечает на вопрос «в чём я сейчас работаю».
//
// Виджет свой, а не поле выбора: раньше здесь стоял `VSelectSearch`, которому гасили рамку,
// отключали чипы, перебивали отступы поля и правили список глобальным блоком по классу — от
// поля выбора оставалась одна механика, зато вся его геометрия продолжала спорить с панелью.
// Теперь это кнопка и меню — ровно то, чем элемент и был: строка панели, открывающая список.
//
// Оба состояния панели устроены одинаково и отличаются только видом кнопки: развёрнутое — плашка,
// имя и шеврон, свёрнутое — одна плашка. Список под ними один и тот же (`nav-flyout`), тот же,
// которым панель показывает свёрнутые группы меню.
//
// Набор подгружается сам: месту применения не нужно знать, грузил ли кто-то пространства раньше.
import { computed, onMounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { IconChevronDown, IconPlus, IconStack2 } from '@tabler/icons-vue'

import IconSwatch from '@/components/IconSwatch.vue'
import { useWorkspaceContextStore } from '../stores/workspace-context.store'

const props = withDefaults(defineProps<{
  /** Панель свёрнута в полосу: видна только плашка текущего пространства. */
  collapsed?: boolean
}>(), {
  collapsed: false,
})

const { t } = useI18n()
const store = useWorkspaceContextStore()

onMounted(store.ensure)

// Заглушка показывается только на достоверной пустоте: до ответа бэка приглашение завести первое
// пространство стояло бы при живых уже заведённых.
const noWorkspaces = computed(() => store.isEmpty)
</script>

<template>
  <!-- ── Пространств нет: вместо выбора — дорога к тому, чтобы завести первое ── -->
  <template v-if="noWorkspaces">
    <VTooltip
      v-if="props.collapsed"
      :text="t('workspace.switcher.empty_action')"
      location="end"
      :offset="6"
      content-class="sidebar-tooltip"
    >
      <template #activator="{ props: tip }">
        <RouterLink v-bind="tip" to="/tasks/workspaces" class="ws-rail ws-rail--empty">
          <IconPlus :size="18" :stroke-width="1.7" />
        </RouterLink>
      </template>
    </VTooltip>

    <RouterLink v-else to="/tasks/workspaces" class="ws-empty">
      <IconStack2 :size="18" :stroke-width="1.6" class="ws-empty__icon" />
      <span class="ws-empty__text">
        <span class="ws-empty__title">{{ t('workspace.switcher.empty') }}</span>
        <span class="ws-empty__action">{{ t('workspace.switcher.empty_action') }}</span>
      </span>
    </RouterLink>
  </template>

  <!-- ── Есть из чего выбирать: кнопка текущего пространства и список под ней ── -->
  <VMenu
    v-else
    :location="props.collapsed ? 'end' : 'bottom'"
    :offset="props.collapsed ? 8 : 4"
    open-on-click
  >
    <template #activator="{ props: menu }">
      <button
        v-bind="menu"
        type="button"
        :class="props.collapsed ? 'ws-rail' : 'ws-trigger'"
        :aria-label="t('workspace.switcher.label')"
      >
        <IconSwatch
          v-if="store.currentWorkspace"
          :icon="store.currentWorkspace.icon"
          :color="store.currentWorkspace.color"
          :width="props.collapsed ? 22 : 20"
        />
        <IconStack2 v-else :size="18" :stroke-width="1.7" />

        <template v-if="!props.collapsed">
          <span class="ws-trigger__title">{{ store.currentWorkspace?.title }}</span>
          <IconChevronDown :size="16" :stroke-width="1.7" class="ws-trigger__caret" />
        </template>
      </button>
    </template>

    <div class="nav-flyout">
      <div class="nav-flyout__title">{{ t('workspace.switcher.label') }}</div>
      <VList density="compact" nav class="nav-flyout__list">
        <VListItem
          v-for="workspace in store.items"
          :key="workspace.code"
          :active="workspace.code === store.current"
          :title="workspace.title"
          rounded="lg"
          class="nav-item"
          @click="store.select(workspace.code)"
        >
          <template #prepend>
            <IconSwatch :icon="workspace.icon" :color="workspace.color" :width="20" />
          </template>
        </VListItem>
      </VList>
    </div>
  </VMenu>
</template>

<style scoped>
/* ── Развёрнутая панель ─────────────────────────────────────────────────────── */
/* Коробка повторяет пункт меню (`.nav-item` в main.scss: 36px, тот же радиус, тот же шрифт):
   элемент стоит над ними одним столбцом, и своя метрика увела бы его из их ряда. Боковое поле —
   8px, как у пункта, поэтому плашка встаёт на одну вертикаль с иконками разделов. */
.ws-trigger {
  display: flex;
  align-items: center;
  gap: 10px;
  width: 100%;
  min-height: 36px;
  padding-inline: 8px;
  border: 0;
  border-radius: var(--radius-sm);
  background: none;
  color: var(--text);
  cursor: pointer;
  text-align: left;
  transition: background-color 0.15s;
}

.ws-trigger:hover { background-color: var(--surface-hi); }

.ws-trigger__title {
  flex: 1;
  min-width: 0;
  font-size: 13px;
  font-weight: 500;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

/* Шеврон приглушён: он говорит, что список раскроется, но соперничать с именем ему незачем. */
.ws-trigger__caret {
  flex: none;
  color: var(--text-faint);
}

/* ── Свёрнутая полоса ──────────────────────────────────────────────────────── */
/* Коробка повторяет пункт меню в полосе (`.nav-item--collapsed`): элемент стоит с ними в
   одном столбце, и своя ширина увела бы его иконку с общей оси. */
.ws-rail {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 100%;
  min-height: 36px;
  border: 0;
  background: none;
  border-radius: var(--radius-sm);
  color: var(--text-muted);
  cursor: pointer;
  transition: background-color 0.15s, color 0.15s;
}

.ws-rail:hover {
  background-color: var(--surface-hi);
  color: var(--text);
}

/* Заглушка в полосе — та же коробка, но с рамкой: пустое место под плашкой иначе читается как
   не загрузившееся, а не как «заводить нечего». */
.ws-rail--empty {
  border: 1px dashed var(--border);
  text-decoration: none;
}

/* ── Заглушка в развёрнутой панели ─────────────────────────────────────────── */
.ws-empty {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 8px 10px;
  border: 1px dashed var(--border);
  border-radius: var(--radius-sm);
  color: var(--text-muted);
  text-decoration: none;
  transition: border-color 0.15s, color 0.15s;
}

.ws-empty:hover {
  border-color: var(--accent);
  color: var(--text);
}

.ws-empty__icon {
  flex: none;
}

.ws-empty__text {
  display: flex;
  flex-direction: column;
  min-width: 0;
}

.ws-empty__title {
  font-size: 12px;
  font-weight: 500;
  color: var(--text);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

/* Приглашение — вторая строка, а не кнопка рядом: вся плашка и есть переход, и кнопка внутри
   ссылки была бы вторым способом сделать то же самое. */
.ws-empty__action {
  font-size: 11px;
  color: var(--accent);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
</style>
